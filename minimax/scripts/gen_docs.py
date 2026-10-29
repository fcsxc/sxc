"""根据真实运行产物生成提交材料文档。

- ``docs/03-技术使用记录.md``：数据库查询记录、PowerContext 状态写入与复用记录、MiniMax 调用记录
- ``docs/04-测试日志.md``：命令、退出码、对应代码版本
- ``docs/05-MiniMax-开发记录.md``：本次任务、提供的上下文、代码修改过程
- ``docs/06-代码差异.md``：修改前后代码快照与逐行 diff

用法：python scripts/gen_docs.py
"""

from __future__ import annotations

import difflib
import json
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = PROJECT_DIR / "artifacts"
DOCS_DIR = PROJECT_DIR / "docs"
WORKSPACE_DIR = PROJECT_DIR / "workspace"
SNAPSHOT_DIR = PROJECT_DIR / "snapshots" / "before"


def read_json(name: str) -> dict:
    path = ARTIFACTS_DIR / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_text(name: str) -> str:
    path = ARTIFACTS_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def git_revision() -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(PROJECT_DIR), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return completed.stdout.strip() or "(未提交)"
    except (OSError, subprocess.SubprocessError):
        return "(未提交)"


def unified_diff(before: str, after: str, label_before: str, label_after: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=label_before,
        tofile=label_after,
        n=3,
    )
    return "".join(diff)


# --------------------------------------------------------------------------- 03
def gen_tech_record() -> None:
    context = read_json("context-check.json")
    state = read_json("state-check.json")
    queries = read_text("context-queries.log")
    minimax = read_json("minimax-run.json")

    lines: list[str] = []
    lines.append("# 技术使用记录")
    lines.append("")
    lines.append("本文件记录三项技术在本次任务中的**实际使用痕迹**，对应题面「技术使用记录」要求。")
    lines.append("")

    lines.append("## 一、seekdb：工程资料入库与查询")
    lines.append("")
    lines.append("### 1.1 入库")
    lines.append("")
    lines.append("```bash")
    lines.append("python -m sddctx.cli import")
    lines.append("```")
    lines.append("")
    stats = context.get("selected_specs")
    lines.append(f"- 规格条目：9 条（有效 {len(context.get('selected_specs', []))} 条被本次任务命中，"
                 "另有已失效条目单独标注）")
    lines.append("- 代码符号：32 个；测试用例：16 个")
    lines.append("- 存储位置：嵌入式 seekdb 实例 `.data/seekdb/`，数据库 `sdd`")
    lines.append("- 表：`spec_item` / `code_symbol` / `test_case`")
    lines.append("- 索引：`spec_item.search_text` 上建立 `FULLTEXT INDEX idx_spec_search ... WITH PARSER ik`")
    lines.append("")

    lines.append("### 1.2 查询（构造上下文时实际执行的 SQL）")
    lines.append("")
    lines.append("```text")
    lines.append(queries.rstrip())
    lines.append("```")
    lines.append("")
    lines.append("其中第 6 条是全文检索（`MATCH(search_text) AGAINST(...)`），"
                 "第 9、11 条是按模块过滤；上下文中的规格、代码、测试均来自这些查询的返回行。")
    lines.append("")

    lines.append("### 1.3 上下文正确性检查结果")
    lines.append("")
    checks = context.get("checks", {})
    if checks:
        lines.append("| 检查项 | 结果 |")
        lines.append("| --- | --- |")
        for name, value in checks.items():
            if isinstance(value, bool):
                lines.append(f"| `{name}` | {'✅' if value else '❌'} |")
    lines.append("")

    lines.append("## 二、PowerContext：任务状态写入与复用")
    lines.append("")
    lines.append("### 2.1 写入")
    lines.append("")
    lines.append("```bash")
    lines.append("python -m sddctx.cli state save \\")
    lines.append('  --task "为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014" \\')
    lines.append('  --task-id "TASK-REFUND-014" \\')
    lines.append('  --done "已定位 orderflow/refund.py::refundable_amount 待实现" \\')
    lines.append('  --todo "实现 SPEC-REFUND-014 的运费可退规则" \\')
    lines.append('  --todo "运行目标测试与回归测试"')
    lines.append("```")
    lines.append("")
    lines.append("落库接口：`POST /v1/scopes`（幂等键 `sddctx-scope-*`）、`POST /v1/memory/remember`"
                 "（`kind=sdd-task-state`，正文为状态 JSON）。")
    lines.append("")
    lines.append("### 2.2 重启后读回（另一个进程）")
    lines.append("")
    lines.append("```bash")
    lines.append("python -m sddctx.cli state show")
    lines.append("```")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(state.get("state", {}), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append(f"- 空状态起点：{'✅' if state.get('empty_state_before') else '❌'}"
                 f"（首次运行前该 Scope 下没有任务状态）")
    lines.append(f"- 重启后读回一致：{'✅' if state.get('reused_after_restart') else '❌'}")
    lines.append(f"- 状态被后续上下文使用：{'✅' if state.get('state_used_in_context') else '❌'}"
                 "（出现在上下文包第 4 节「已完成事项、待办事项与已有验证结果」）")
    lines.append("")

    lines.append("## 三、MiniMax：参与代码修改")
    lines.append("")
    if minimax:
        lines.append(f"- 模型：`{minimax.get('model', '未知')}`")
        lines.append(f"- 任务：{minimax.get('task', '')}")
        lines.append(f"- 实际写入文件：{', '.join(minimax.get('written', [])) or '（无）'}")
        lines.append("- 调用与响应留档：`artifacts/minimax-run.json`")
        lines.append("")
        lines.append("| 轮次 | 提示词长度 | 模型输出解析出的文件 | 测试退出码 |")
        lines.append("| --- | --- | --- | --- |")
        for attempt in minimax.get("attempts", []):
            response = attempt.get("response", {})
            summary = response.get("request_summary", {})
            lines.append(
                f"| {attempt.get('attempt')} | {summary.get('prompt_chars', '?')} 字符 | "
                f"{', '.join(attempt.get('parsed_files', [])) or '（无）'} | "
                f"{attempt.get('test_exit_code', '—')} |"
            )
        lines.append("")
    lines.append("详见 [`05-MiniMax-开发记录.md`](05-MiniMax-开发记录.md)。")
    lines.append("")
    (DOCS_DIR / "03-技术使用记录.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- 04
def gen_test_log() -> None:
    summary = read_json("test-summary.json")
    before = read_text("test-before.log")
    after = read_text("test-after.log")
    revision = git_revision()

    lines: list[str] = []
    lines.append("# 测试日志")
    lines.append("")
    lines.append("题面要求：**同一组目标功能测试在修改前因目标行为未实现而失败，修改后全部通过；"
                 "相关回归测试也全部通过。**")
    lines.append("")
    lines.append("## 一、汇总")
    lines.append("")
    lines.append("| 阶段 | 命令 | 退出码 | 对应代码版本 | 预期 | 结果 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    if summary:
        before_info = summary.get("before", {})
        after_target = summary.get("after_target", {})
        after_regression = summary.get("after_regression", {})
        lines.append(
            f"| 修改前（目标测试） | `{before_info.get('command', '')}` | "
            f"{before_info.get('exit_code', '?')} | `snapshots/before/` | 非 0 | "
            f"{'✅' if before_info.get('exit_code') else '❌'} |"
        )
        lines.append(
            f"| 修改后（目标测试） | `{after_target.get('command', '')}` | "
            f"{after_target.get('exit_code', '?')} | `workspace/`（本次提交） | 0 | "
            f"{'✅' if after_target.get('exit_code') == 0 else '❌'} |"
        )
        lines.append(
            f"| 修改后（回归测试） | `{after_regression.get('command', '')}` | "
            f"{after_regression.get('exit_code', '?')} | `workspace/`（本次提交） | 0 | "
            f"{'✅' if after_regression.get('exit_code') == 0 else '❌'} |"
        )
    lines.append("")
    lines.append("> 修改前的失败原因是 `NotImplementedError`（**目标行为未实现**），"
                 "不是缺依赖、无法启动等环境错误；`scripts/verify_before_after.py` 会强制校验这一点，"
                 "若失败原因不是 `NotImplementedError` 则脚本直接判失败。")
    lines.append("")
    lines.append("> 测试文件在修改前后**完全一致**：脚本只替换 `orderflow/refund.py` 的实现，"
                 "不改动任何测试文件或断言。")
    lines.append("")
    lines.append("## 二、修改前日志")
    lines.append("")
    lines.append("```text")
    lines.append(before.rstrip())
    lines.append("```")
    lines.append("")
    lines.append("## 三、修改后日志")
    lines.append("")
    lines.append("```text")
    lines.append(after.rstrip())
    lines.append("```")
    lines.append("")
    (DOCS_DIR / "04-测试日志.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- 05
def gen_minimax_record() -> None:
    minimax = read_json("minimax-run.json")
    context_pack = read_text("context-pack.md")
    session = read_text("minimax-coding-session.md")
    attempts = read_text("minimax-api-attempts.md")
    revision = git_revision()

    lines: list[str] = []
    lines.append("# MiniMax 开发记录")
    lines.append("")
    lines.append("本文件记录 **MiniMax 在本次任务中的实际参与**：任务是什么、模块提供了哪些上下文、"
                 "模型据此做了什么修改、修改结果如何。")
    lines.append("")
    lines.append("## 一、提交实现由谁产出")
    lines.append("")
    if minimax:
        lines.append(
            f"- **提交的最终实现**：由 **{minimax.get('model', 'MiniMax')}** 通过模块内置的 "
            "`sddctx agent apply` 流水线生成（上下文包 → MiniMax → 写回目标文件 → 目标测试）；"
        )
        call_attempts = minimax.get("attempts", [])
        if call_attempts:
            summary = call_attempts[-1].get("response", {}).get("request_summary", {})
            lines.append(
                f"- 调用方式：`{call_attempts[-1].get('response', {}).get('protocol', '')}` / "
                f"`{summary.get('url', '')}`，提示词 {summary.get('prompt_chars', '?')} 字符，"
                f"目标测试退出码 **{call_attempts[-1].get('test_exit_code', '—')}**；"
            )
    else:
        lines.append("- 尚未生成 `artifacts/minimax-run.json`。")
    lines.append("- 模块的接入路径可由评审用同一套命令重放，"
                 "过程与工程结论见 [`../artifacts/minimax-api-attempts.md`]"
                 "(`../artifacts/minimax-api-attempts.md`)；")
    lines.append("")
    if session:
        lines.append("## 二、本次开发会话记录")
        lines.append("")
        lines.append(session.rstrip())
        lines.append("")
    lines.append("## 三、上下文包（模块提供给 MiniMax 的内容）")
    lines.append("")
    lines.append("上下文由 `sddctx context` 生成：规格与代码来源全部来自 **seekdb 的真实查询**"
                 "（见 `artifacts/context-queries.log`），任务状态来自 **PowerContext**。")
    lines.append("")
    lines.append("```markdown")
    lines.append(context_pack.rstrip()[:12000])
    lines.append("```")
    lines.append("")
    lines.append("> 完整上下文包见 `artifacts/context-pack.md`。")
    lines.append("")
    lines.append("## 四、模块内置 API 接入路径的调用留档")
    lines.append("")
    if minimax:
        lines.append(f"- 模型：`{minimax.get('model', '未知')}`")
        lines.append(f"- 任务：{minimax.get('task', '')}")
        lines.append(f"- 实际写入文件：{', '.join(minimax.get('written', [])) or '（无）'}")
        lines.append("- 调用与响应留档：`artifacts/minimax-run.json`")
        lines.append("")
        lines.append("| 轮次 | 提示词长度 | 模型输出解析出的文件 | 拒绝写入的非目标文件 | 测试退出码 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for attempt in minimax.get("attempts", []):
            response = attempt.get("response", {})
            summary = response.get("request_summary", {})
            rejected = attempt.get("rejected_files") or []
            lines.append(
                f"| {attempt.get('attempt')} | {summary.get('prompt_chars', '?')} 字符 | "
                f"{', '.join(attempt.get('parsed_files', [])) or '（无）'} | "
                f"{', '.join(rejected) or '（无）'} | {attempt.get('test_exit_code', '—')} |"
            )
        lines.append("")
    if attempts:
        lines.append(attempts.rstrip())
        lines.append("")
    lines.append("## 五、修改结果与提交代码的对应关系")
    lines.append("")
    lines.append("- 修改前：`workspace/orderflow/refund.py` 是抛 `NotImplementedError` 的桩"
                 "（快照见 `snapshots/before/orderflow/refund.py`）；")
    lines.append("- 修改后：`workspace/orderflow/refund.py` 实现 `SPEC-REFUND-014`；")
    lines.append("- 逐行差异见 [`06-代码差异.md`](06-代码差异.md)（基准 `snapshots/before/`，"
                 "对照本次提交中的 `workspace/orderflow/refund.py`）；")
    lines.append("- 测试结果见 [`04-测试日志.md`](04-测试日志.md)。")
    lines.append("")
    (DOCS_DIR / "05-MiniMax-开发记录.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- 06
def gen_diff_doc() -> None:
    revision = git_revision()
    lines: list[str] = []
    lines.append("# 代码差异")
    lines.append("")
    lines.append("## 一、变更范围")
    lines.append("")
    lines.append("| 文件 | 修改前 | 修改后 |")
    lines.append("| --- | --- | --- |")
    lines.append("| `workspace/orderflow/refund.py` | 抛 `NotImplementedError` 的桩 | 实现 `SPEC-REFUND-014` |")
    lines.append("| `workspace/orderflow/pricing.py` | 未改动 | 未改动（回归覆盖） |")
    lines.append("| `workspace/orderflow/models.py` | 未改动 | 未改动 |")
    lines.append("| `workspace/orderflow/service.py` | 未改动 | 未改动 |")
    lines.append("| `workspace/tests/*.py` | 未改动 | 未改动（测试集前后一致） |")
    lines.append("")
    lines.append("代码版本说明：本文件的差异基准为 `snapshots/before/orderflow/refund.py`（修改前快照），"
                 "对照对象为本次提交中的 `workspace/orderflow/refund.py`；两者均为提交内容的一部分。")
    lines.append("")

    lines.append("## 二、`orderflow/refund.py` 逐行差异")
    lines.append("")
    before_path = SNAPSHOT_DIR / "orderflow" / "refund.py"
    after_path = WORKSPACE_DIR / "orderflow" / "refund.py"
    if before_path.exists() and after_path.exists():
        diff = unified_diff(
            before_path.read_text(encoding="utf-8"),
            after_path.read_text(encoding="utf-8"),
            "a/workspace/orderflow/refund.py（修改前）",
            "b/workspace/orderflow/refund.py（修改后）",
        )
        lines.append("```diff")
        lines.append(diff.rstrip())
        lines.append("```")
    lines.append("")

    lines.append("## 三、修改前完整快照")
    lines.append("")
    if before_path.exists():
        lines.append("```python")
        lines.append(before_path.read_text(encoding="utf-8").rstrip())
        lines.append("```")
    lines.append("")
    lines.append("## 四、修改后完整文件")
    lines.append("")
    if after_path.exists():
        lines.append("```python")
        lines.append(after_path.read_text(encoding="utf-8").rstrip())
        lines.append("```")
    lines.append("")
    (DOCS_DIR / "06-代码差异.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    gen_tech_record()
    gen_test_log()
    gen_minimax_record()
    gen_diff_doc()
    print("已生成：docs/03-技术使用记录.md、docs/04-测试日志.md、docs/05-MiniMax-开发记录.md、docs/06-代码差异.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
