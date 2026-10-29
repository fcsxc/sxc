"""把工程资料解析成可入库的结构化记录。

三类资料：
- 规格条目：``workspace/specs/*.md``（YAML 风格 front-matter + Markdown 正文）
- 代码符号：``workspace/**/*.py``（用 :mod:`ast` 提取函数 / 类 / 方法）
- 测试用例：``workspace/tests/test_*.py``
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .models import CodeSymbol, SpecItem, TestCase

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def _split_list(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,;]", value) if part.strip()]


def parse_spec_file(path: Path, root: Path) -> SpecItem:
    """解析一个规格文件。"""

    raw = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(raw)
    if not match:
        raise ValueError(f"规格文件缺少 front-matter: {path}")
    head, body = match.group(1), match.group(2)
    fields: dict[str, str] = {}
    for line in head.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"').strip("'")
    spec_id = fields.get("id", "").strip()
    if not spec_id:
        raise ValueError(f"规格条目缺少 id: {path}")
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = path.name
    return SpecItem(
        spec_id=spec_id,
        title=fields.get("title", spec_id),
        status=fields.get("status", "active").strip().lower(),
        applies_to=_split_list(fields.get("applies_to", "")),
        supersedes=_split_list(fields.get("supersedes", "")),
        tags=_split_list(fields.get("tags", "")),
        source_path=relative,
        body=body.strip(),
        revision=1,
    )


def load_specs(specs_dir: Path, root: Path) -> list[SpecItem]:
    """加载目录下全部规格条目。"""

    items: list[SpecItem] = []
    for path in sorted(Path(specs_dir).glob("*.md")):
        items.append(parse_spec_file(path, root))
    return items


def module_path_for(path: Path, root: Path) -> str:
    """``workspace/orderflow/refund.py`` -> ``orderflow.refund``。"""

    relative = path.resolve().relative_to(Path(root).resolve()).as_posix()
    if relative.endswith(".py"):
        relative = relative[: -len(".py")]
    if relative.endswith("/__init__"):
        relative = relative[: -len("/__init__")]
    return relative.replace("/", ".")


def _docstring_of(node: ast.AST) -> str:
    try:
        doc = ast.get_docstring(node)  # type: ignore[arg-type]
    except TypeError:
        return ""
    return (doc or "").strip()


def _signature_of(source_lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1) - 1
    end = getattr(node, "end_lineno", getattr(node, "lineno", 1))
    chunk = " ".join(line.strip() for line in source_lines[start:end][:1])
    return chunk.rstrip(":")


def parse_code_file(path: Path, root: Path) -> list[CodeSymbol]:
    """提取一个 Python 文件中的符号。"""

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    source_lines = source.splitlines()
    module = module_path_for(path, root)
    relative = path.resolve().relative_to(Path(root).resolve()).as_posix()
    symbols: list[CodeSymbol] = []

    def visit(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{scope}.{child.name}" if scope else child.name
                kind = "method" if scope else "function"
                symbols.append(
                    CodeSymbol(
                        symbol_id=f"{module}:{qualified}",
                        file_path=relative,
                        module_path=module,
                        name=child.name,
                        kind=kind,
                        signature=_signature_of(source_lines, child),
                        docstring=_docstring_of(child),
                        line_start=child.lineno,
                        line_end=getattr(child, "end_lineno", child.lineno),
                        source="\n".join(source_lines[child.lineno - 1 : getattr(child, "end_lineno", child.lineno)]),
                    )
                )
                visit(child, qualified)
            elif isinstance(child, ast.ClassDef):
                qualified = f"{scope}.{child.name}" if scope else child.name
                symbols.append(
                    CodeSymbol(
                        symbol_id=f"{module}:{qualified}",
                        file_path=relative,
                        module_path=module,
                        name=child.name,
                        kind="class",
                        signature=_signature_of(source_lines, child),
                        docstring=_docstring_of(child),
                        line_start=child.lineno,
                        line_end=getattr(child, "end_lineno", child.lineno),
                        source="\n".join(source_lines[child.lineno - 1 : getattr(child, "end_lineno", child.lineno)]),
                    )
                )
                visit(child, qualified)

    visit(tree, "")
    return symbols


def load_code_symbols(code_dir: Path, root: Path) -> list[CodeSymbol]:
    """加载目录下全部代码符号。"""

    symbols: list[CodeSymbol] = []
    for path in sorted(Path(code_dir).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        symbols.extend(parse_code_file(path, root))
    return symbols


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
    seen: list[str] = []
    for module in modules:
        root = module.split(".")[0]
        if root == "orderflow" and module not in seen:
            seen.append(module)
    return seen


def parse_test_file(path: Path, root: Path) -> list[TestCase]:
    """提取测试文件中的测试用例。"""

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    source_lines = source.splitlines()
    relative = path.resolve().relative_to(Path(root).resolve()).as_posix()
    targets = _imported_modules(tree)
    primary = next((m for m in targets if m not in {"orderflow.models", "orderflow"}), targets[0] if targets else "")
    cases: list[TestCase] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue
        asserts = [
            source_lines[stmt.lineno - 1].strip()
            for stmt in ast.walk(node)
            if isinstance(stmt, ast.Assert)
        ]
        cases.append(
            TestCase(
                test_id=f"{relative}::{node.name}",
                file_path=relative,
                name=node.name,
                module_path=primary,
                docstring=_docstring_of(node),
                asserts="; ".join(asserts),
                target_modules=list(targets),
            )
        )
    return cases


def load_test_cases(tests_dir: Path, root: Path) -> list[TestCase]:
    """加载目录下全部测试用例。"""

    cases: list[TestCase] = []
    for path in sorted(Path(tests_dir).rglob("test_*.py")):
        cases.extend(parse_test_file(path, root))
    return cases
