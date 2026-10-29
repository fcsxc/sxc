"""上下文包渲染：把 ContextPack 输出成给开发助手阅读的 Markdown。"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .models import ContextPack


def render_context_pack(pack: ContextPack, *, source_label: str = "seekdb 嵌入式实例") -> str:
    """渲染上下文包。"""

    lines: list[str] = []
    lines.append("# 开发上下文包")
    lines.append("")
    lines.append(f"- 任务：{pack.task}")
    lines.append(f"- 生成时间：{dt.datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- 规格与代码来源：{source_label}")
    lines.append(f"- 焦点模块：{', '.join(pack.modules) if pack.modules else '（无）'}")
    lines.append("")

    lines.append("## 1. 本次任务适用的规格条目")
    lines.append("")
    if pack.specs:
        for spec in pack.specs:
            lines.append(
                f"### {spec['spec_id']} {spec['title']}"
                f"（来源：`{spec['source_path']}`，状态：{spec['status']}，版本：rev{spec['revision']}，"
                f"相关度：{spec.get('score', 0)}）"
            )
            lines.append("")
            lines.append(spec["body"].strip())
            lines.append("")
            if spec["applies_to"]:
                lines.append(f"- 适用模块：{', '.join(spec['applies_to'])}")
            if spec["supersedes"]:
                lines.append(f"- 取代：{', '.join(spec['supersedes'])}")
            lines.append("")
    else:
        lines.append("（没有命中任何当前有效的规格条目）")
        lines.append("")

    if pack.superseded_specs:
        lines.append("### 已失效的决策（仅供追溯，**不得**作为约束）")
        lines.append("")
        for spec in pack.superseded_specs:
            replaced = "，已被 ".join(spec["supersedes"]) if spec["supersedes"] else ""
            lines.append(
                f"- `{spec['spec_id']}` {spec['title']}（来源：`{spec['source_path']}`，状态：{spec['status']}{replaced}）"
            )
        lines.append("")

    lines.append("## 2. 需要修改的代码文件与符号")
    lines.append("")
    if pack.symbols:
        for symbol in pack.symbols:
            lines.append(
                f"### `{symbol['file_path']}` :: `{symbol['name']}`"
                f"（{symbol['kind']}，第 {symbol['line_start']}-{symbol['line_end']} 行，"
                f"模块 `{symbol['module_path']}`，相关度：{symbol.get('score', 0)}）"
            )
            lines.append("")
            if symbol["docstring"]:
                lines.append(symbol["docstring"].strip())
                lines.append("")
            lines.append("```python")
            lines.append(symbol["source"].rstrip())
            lines.append("```")
            lines.append("")
    else:
        lines.append("（没有命中代码符号）")
        lines.append("")

    lines.append("## 3. 用于验证功能与兼容性的测试")
    lines.append("")
    if pack.tests:
        for case in pack.tests:
            lines.append(
                f"### `{case['file_path']}` :: `{case['name']}`"
                f"（被测模块：{', '.join(case['target_modules']) or case['module_path']}，"
                f"相关度：{case.get('score', 0)}）"
            )
            lines.append("")
            if case["docstring"]:
                lines.append(case["docstring"].strip())
                lines.append("")
            if case["asserts"]:
                lines.append("断言要点：")
                lines.append("")
                lines.append("```python")
                lines.append(case["asserts"])
                lines.append("```")
                lines.append("")
    else:
        lines.append("（没有命中测试用例）")
        lines.append("")

    lines.append("## 4. 已完成事项、待办事项与已有验证结果")
    lines.append("")
    state = pack.state or {}
    done = state.get("done", [])
    todo = state.get("todo", [])
    verifications = state.get("verifications", [])
    if state:
        lines.append(f"- 任务标识：`{state.get('task_id', '')}`")
        lines.append(f"- 状态更新时间：{state.get('updated_at', '')}")
        lines.append(f"- 上下文指纹：`{state.get('context_digest', '')}`")
        lines.append("")
    lines.append("### 已完成")
    lines.append("")
    lines.extend([f"- {item}" for item in done] or ["- （无）"])
    lines.append("")
    lines.append("### 待办")
    lines.append("")
    lines.extend([f"- {item}" for item in todo] or ["- （无）"])
    lines.append("")
    lines.append("### 已有验证结果")
    lines.append("")
    if verifications:
        for item in verifications:
            lines.append(
                f"- {item.get('name', '')}：命令 `{item.get('command', '')}`，"
                f"退出码 {item.get('exit_code', '未知')}，时间 {item.get('at', '')}"
            )
    else:
        lines.append("- （无）")
    lines.append("")

    return "\n".join(lines)


def render_context_json(pack: ContextPack) -> str:
    """渲染机器可读的上下文（JSON）。"""

    import json

    return json.dumps(pack.to_dict(), ensure_ascii=False, indent=2)


def summarize(pack: ContextPack) -> dict[str, Any]:
    """上下文摘要（用于命令行输出）。"""

    state = pack.state or {}
    return {
        "task": pack.task,
        "modules": pack.modules,
        "specs": [spec["spec_id"] for spec in pack.specs],
        "superseded": [spec["spec_id"] for spec in pack.superseded_specs],
        "symbols": [f"{symbol['file_path']}::{symbol['name']}" for symbol in pack.symbols],
        "tests": [f"{case['file_path']}::{case['name']}" for case in pack.tests],
        "state": {
            "task_id": state.get("task_id", ""),
            "done": state.get("done", []),
            "todo": state.get("todo", []),
            "verifications": state.get("verifications", []),
            "updated_at": state.get("updated_at", ""),
        },
        "queries": len(pack.queries),
    }
