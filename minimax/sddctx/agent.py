"""MiniMax 接入：把上下文包交给 MiniMax 完成代码修改。

支持两种协议（通过 ``MINIMAX_PROTOCOL`` 选择）：

- ``minimax``（默认）：``POST {base_url}/text/chatcompletion_v2``
- ``anthropic``：``POST {base_url}/messages``（Anthropic 兼容接口）

凭据从环境变量 ``MINIMAX_API_KEY`` 读取，不写入仓库。
"""

from __future__ import annotations

import ast
import builtins
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config

FILE_BLOCK_RE = re.compile(
    r"###\s*FILE:\s*(?P<path>[^\n]+)\n(?P<body>.*?)(?=\n###\s*FILE:|\Z)",
    re.DOTALL,
)
CODE_BLOCK_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]*)\n(?P<body>.*?)```", re.DOTALL)


class MiniMaxError(RuntimeError):
    """MiniMax 调用失败。"""


def _key_from_mmx_config() -> str:
    """复用官方 mmx CLI 已配置的凭据（``~/.mmx/config.json``）。"""

    try:
        from pathlib import Path

        path = Path.home() / ".mmx" / "config.json"
        if not path.exists():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
        key = data.get("api_key")
        return key if isinstance(key, str) else ""
    except (OSError, json.JSONDecodeError):
        return ""


@dataclass
class MiniMaxResponse:
    """一次 MiniMax 调用的结果（用于留档）。"""

    model: str
    protocol: str
    content: str
    usage: dict[str, Any] = field(default_factory=dict)
    request_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "protocol": self.protocol,
            "content": self.content,
            "usage": self.usage,
            "request_summary": self.request_summary,
        }


class MiniMaxClient:
    """MiniMax 文本模型客户端。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        protocol: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get(config.MINIMAX_API_KEY_ENV, "") or _key_from_mmx_config()
        self.base_url = (base_url or config.MINIMAX_BASE_URL).rstrip("/")
        self.model = model or config.MINIMAX_MODEL
        self.protocol = (protocol or os.environ.get("MINIMAX_PROTOCOL", "minimax")).lower()
        self.timeout = timeout or config.MINIMAX_TIMEOUT
        if not self.api_key:
            raise MiniMaxError(
                f"未找到 MiniMax 凭据：请设置环境变量 {config.MINIMAX_API_KEY_ENV}"
                "（或先执行 mmx auth login，模块会复用 ~/.mmx/config.json 中的 key）"
            )

    # ------------------------------------------------------------------ 调用
    def chat(self, prompt: str, system: str | None = None) -> MiniMaxResponse:
        """调用 MiniMax 生成文本。"""

        if self.protocol == "anthropic":
            return self._chat_anthropic(prompt, system)
        return self._chat_minimax(prompt, system)

    def _chat_minimax(self, prompt: str, system: str | None) -> MiniMaxResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model, "messages": messages, "stream": False}
        url = f"{self.base_url}/text/chatcompletion_v2"
        response = self._post(url, payload, {"Authorization": f"Bearer {self.api_key}"})
        base_resp = response.get("base_resp") or {}
        status = base_resp.get("status_code")
        if status not in (0, None):
            raise MiniMaxError(f"MiniMax 返回错误：{base_resp}")
        choices = response.get("choices") or []
        if not choices:
            raise MiniMaxError(f"MiniMax 未返回内容：{str(response)[:300]}")
        content = ((choices[0].get("message") or {}).get("content")) or ""
        return MiniMaxResponse(
            model=self.model,
            protocol="minimax",
            content=content,
            usage=response.get("usage") or {},
            request_summary={
                "url": url,
                "model": self.model,
                "prompt_chars": len(prompt),
                "system_chars": len(system or ""),
                "messages": len(messages),
            },
        )

    def _chat_anthropic(self, prompt: str, system: str | None) -> MiniMaxResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        url = f"{self.base_url}/messages"
        response = self._post(
            url,
            payload,
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        blocks = response.get("content") or []
        content = "".join(block.get("text", "") for block in blocks if isinstance(block, dict))
        return MiniMaxResponse(
            model=self.model,
            protocol="anthropic",
            content=content,
            usage=response.get("usage") or {},
            request_summary={
                "url": url,
                "model": self.model,
                "prompt_chars": len(prompt),
                "system_chars": len(system or ""),
            },
        )

    def _post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged = {"Content-Type": "application/json", "Accept": "application/json"}
        merged.update(headers)
        request = urllib.request.Request(url, data=data, method="POST", headers=merged)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise MiniMaxError(f"POST {url} -> HTTP {exc.code}: {detail[:400]}") from exc
        except urllib.error.URLError as exc:
            raise MiniMaxError(f"POST {url} -> 网络错误：{exc.reason}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MiniMaxError(f"MiniMax 返回非 JSON 内容：{body[:200]}") from exc


class MmxCliClient:
    """通过官方 ``mmx`` CLI 调用 MiniMax。

    命令形态（与大赛官方做法一致）::

        mmx text chat --messages-file <file> --model <model> \\
            --max-tokens 4096 --temperature 0.2 --non-interactive --quiet --output text

    凭据由 mmx CLI 自己管理（``~/.mmx/config.json``），不经过本模块。
    """

    def __init__(
        self,
        model: str | None = None,
        binary: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        timeout: float | None = None,
    ) -> None:
        self.model = model or config.MINIMAX_MODEL
        self.binary = binary or os.environ.get("MMX_BIN", "mmx")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout or config.MINIMAX_TIMEOUT

    def chat(self, prompt: str, system: str | None = None) -> MiniMaxResponse:
        """调用 mmx CLI 生成文本。"""

        import subprocess
        import tempfile

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", encoding="utf-8", delete=False
        ) as handle:
            json.dump(messages, handle, ensure_ascii=False)
            messages_file = handle.name
        try:
            import shutil

            resolved = shutil.which(self.binary) or self.binary
            command = [
                resolved,
                "text",
                "chat",
                "--messages-file",
                messages_file,
                "--model",
                self.model,
                "--max-tokens",
                str(self.max_tokens),
                "--temperature",
                str(self.temperature),
                "--non-interactive",
                "--quiet",
                "--output",
                "text",
            ]
            # Windows 上的 npm 全局命令是 .cmd 垫片，必须交给 shell 执行
            use_shell = os.name == "nt" and resolved.lower().endswith((".cmd", ".bat"))
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=use_shell,
            )
        except FileNotFoundError as exc:
            raise MiniMaxError(
                f"找不到 {self.binary} 命令；请先安装官方 CLI：npm i -g @minimax/mmx-cli"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MiniMaxError(f"{self.binary} 调用超时（{self.timeout}s）") from exc
        finally:
            try:
                Path(messages_file).unlink()
            except OSError:  # pragma: no cover
                pass

        if completed.returncode != 0:
            raise MiniMaxError(
                f"{self.binary} 返回 {completed.returncode}: {(completed.stderr or '')[:400]}"
            )
        content = completed.stdout or ""
        return MiniMaxResponse(
            model=self.model,
            protocol="mmx-cli",
            content=content.strip(),
            usage={},
            request_summary={
                "command": " ".join(command[:6]) + " ...",
                "model": self.model,
                "prompt_chars": len(prompt),
                "system_chars": len(system or ""),
                "messages": len(messages),
            },
        )


# ---------------------------------------------------------------------- 提示词
SYSTEM_PROMPT = (
    "你是资深 Python 工程师，正在按规格驱动开发（SDD）的方式修改一个已有工程。"
    "你必须严格按照「开发上下文包」中给出的规格条目实现，"
    "不要引入上下文里没有的规则，也不要修改上下文未要求的文件。"
)


def public_api_hints(files: dict[str, str]) -> list[str]:
    """从参考文件里提取各模块的公开接口（模块路径 + 名字 + 签名）。

    用来明确告诉模型「哪些函数/常量已经存在、签名长什么样、必须显式 import 后使用」，
    避免出现「调用了但没导入」「调用参数不对」这类错误。
    """

    hints: list[str] = []
    for path, content in files.items():
        module = path.replace("/", ".").removesuffix(".py").removesuffix(".__init__")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        entries: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    entries.append(f"{node.name}{_signature(node)}")
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    entries.append(node.name)
            elif isinstance(node, ast.Assign):
                entries.extend(
                    target.id
                    for target in node.targets
                    if isinstance(target, ast.Name) and target.id.isupper()
                )
        if entries:
            hints.append(f"- {module}：" + ", ".join(entries))
    return hints


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [arg.arg for arg in node.args.args]
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    for arg in node.args.kwonlyargs:
        args.append(arg.arg)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    return "(" + ", ".join(args) + ")"


def undefined_names(source: str) -> list[str]:
    """返回模块里「使用但没有定义也没有导入」的名字。

    这是给开发助手的静态反馈：模型经常会调用了既有函数却忘了 import，
    这里把它指出来，助手就能在下一轮补上。
    """

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    defined: set[str] = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                defined.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, (ast.comprehension,)):
            for inner in ast.walk(node.target):
                if isinstance(inner, ast.Name):
                    defined.add(inner.id)
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    return sorted(used - defined)


def suggested_imports(target_path: str, files: dict[str, str]) -> list[str]:
    """根据目标文件所在包，给出可直接照抄的 import 语句。

    依据是工程里真实存在的模块与顶层名字，不做任何臆测。
    """

    target_module = target_path.replace("/", ".").removesuffix(".py")
    package = target_module.rsplit(".", 1)[0] if "." in target_module else ""
    lines: list[str] = []
    for path, content in files.items():
        module = path.replace("/", ".").removesuffix(".py").removesuffix(".__init__")
        if module == target_module:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        names: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    names.append(node.name)
            elif isinstance(node, ast.Assign):
                names.extend(
                    target.id
                    for target in node.targets
                    if isinstance(target, ast.Name) and target.id.isupper()
                )
        if not names:
            continue
        if package and module.startswith(package + "."):
            relative = "." + module[len(package) + 1 :]
        else:
            relative = module
        lines.append(f"from {relative} import " + ", ".join(names))
    return lines


def known_signatures(files: dict[str, str]) -> dict[str, tuple[str, list[str]]]:
    """收集参考文件里顶层函数的「名字 -> (模块, 参数名列表)」。"""

    table: dict[str, tuple[str, list[str]]] = {}
    for path, content in files.items():
        module = path.replace("/", ".").removesuffix(".py").removesuffix(".__init__")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                args.extend(arg.arg for arg in node.args.kwonlyargs)
                table.setdefault(node.name, (module, args))
    return table


def signature_mismatches(source: str, files: dict[str, str]) -> list[str]:
    """找出对既有函数的调用与真实签名不符的地方。

    这是给开发助手的第二类静态反馈：模型经常按直觉调用既有函数（例如把
    ``{sku: 数量}`` 整个字典传给按 sku 分摊的函数），这里把真实签名摆出来。
    """

    table = known_signatures(files)
    if not table:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        entry = table.get(node.func.id)
        if entry is None:
            continue
        module, params = entry
        if any(param.startswith("*") for param in params):
            continue
        positional = len(node.args)
        keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
        supplied = positional + len(keywords)
        required = len(params)
        if supplied != required:
            problems.append(
                f"`{node.func.id}` 定义在 `{module}`，真实签名是 ({', '.join(params)})，"
                f"当前调用只给了 {supplied} 个参数"
            )
        unknown = sorted(keywords - set(params))
        if unknown:
            problems.append(
                f"`{node.func.id}` 定义在 `{module}`，真实签名是 ({', '.join(params)})，"
                f"当前调用传了不存在的关键字参数 {', '.join(unknown)}"
            )
    return sorted(set(problems))


def build_prompt(
    task: str,
    context_markdown: str,
    target_files: dict[str, str],
    feedback: str | None = None,
    reference_files: dict[str, str] | None = None,
) -> str:
    """构造给 MiniMax 的提示词。"""

    parts: list[str] = []
    parts.append("# 任务\n")
    parts.append(task.strip())
    parts.append("\n# 硬性约束\n")
    parts.append(f"- **只允许修改这些文件**：{', '.join(target_files) or '（无）'}。\n")
    parts.append("- 其它文件（包括参考文件、测试文件）只能读取，绝对不要修改，也不要输出它们。\n")
    parts.append("- 必须复用工程中已经存在的函数，不要修改它们的名称、签名或行为；"
                 "如果缺少能力，只在允许修改的文件内补齐。\n")
    parts.append("- 不要修改、删除或跳过任何测试断言。\n")
    parts.append("- 新写的代码必须**显式 import** 所有用到的名字（函数、常量、模型类），"
                 "不允许依赖未导入的名字。\n")
    if reference_files:
        hints = public_api_hints(reference_files)
        if hints:
            parts.append("\n# 可直接复用的既有接口（需要显式 import 后调用）\n")
            parts.extend(hints)
            parts.append("")
        imports = suggested_imports(next(iter(target_files), ""), dict(reference_files))
        if imports:
            parts.append("\n# 建议的 import 语句（按工程实际结构生成，可直接使用）\n")
            parts.append("```python")
            parts.extend(imports)
            parts.append("```")
            parts.append("")
    parts.append("\n# 开发上下文包\n")
    parts.append(context_markdown.strip())
    parts.append("\n# 需要你修改的文件（当前内容）\n")
    for path, content in target_files.items():
        parts.append(f"\n## {path}\n")
        parts.append("```python")
        parts.append(content.rstrip())
        parts.append("```")
    if reference_files:
        parts.append("\n# 只读参考文件（不要修改）\n")
        for path, content in reference_files.items():
            parts.append(f"\n## {path}\n")
            parts.append("```python")
            parts.append(content.rstrip())
            parts.append("```")
    if feedback:
        parts.append("\n# 上一次尝试的测试反馈（请据此修正）\n")
        parts.append(feedback.strip())
    parts.append(
        "\n# 输出要求\n"
        "请输出修改后的完整文件内容，每个文件用如下格式包裹，路径必须是相对仓库根目录的路径：\n"
        "### FILE: <相对路径>\n"
        "```python\n"
        "<完整文件内容>\n"
        "```\n"
        "只输出需要修改的文件，不要输出解释性文字。"
    )
    return "\n".join(parts)


def extract_files(text: str, fallback_path: str | None = None) -> dict[str, str]:
    """从模型输出里解析出文件内容。

    优先识别 ``### FILE: <路径>`` + 代码块的格式；若模型只给了一个代码块，
    且调用方声明了唯一的目标文件，则把该代码块视为目标文件的新内容。
    """

    files: dict[str, str] = {}
    for match in FILE_BLOCK_RE.finditer(text):
        path = match.group("path").strip().strip("`")
        body = match.group("body")
        code = CODE_BLOCK_RE.search(body)
        content = code.group("body") if code else body
        files[path] = content.strip("\n") + "\n"
    if not files and fallback_path:
        blocks = CODE_BLOCK_RE.findall(text)
        if len(blocks) == 1:
            files[fallback_path] = blocks[0].strip("\n") + "\n"
    return files


def write_files(
    root: Path,
    files: dict[str, str],
    *,
    dry_run: bool = False,
    allowed: set[str] | None = None,
) -> list[str]:
    """把模型给出的文件写回工程；返回被写入的相对路径。

    ``allowed`` 非空时，只有白名单内的文件会被写入——防止模型顺手改动
    测试文件或其它回归文件。
    """

    written: list[str] = []
    for relative, content in files.items():
        if allowed is not None and relative not in allowed:
            raise ValueError(f"拒绝写入非目标文件：{relative}")
        target = (root / relative).resolve()
        root_resolved = root.resolve()
        if root_resolved not in target.parents and target != root_resolved:
            raise ValueError(f"拒绝写入工程之外的路径：{relative}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        written.append(relative)
    return written
