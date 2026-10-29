"""验证验收项「状态能够复用」。

流程（每一步都是独立的进程，模拟模块重启）：
1. 检查 PowerContext 当前没有本任务的状态（空状态起点）；
2. 用一个进程写入任务状态；
3. 用另一个进程读回，断言已完成 / 待办 / 验证结果一致；
4. 再用一个进程构造上下文，断言状态出现在上下文第 4 节里（被真正使用）。

运行结果写入 ``artifacts/state-check.json``。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = PROJECT_DIR / "artifacts"
TASK = "为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014"

DONE = ["已定位 orderflow/refund.py::refundable_amount 待实现"]
TODO = ["实现 SPEC-REFUND-014 的运费可退规则", "运行目标测试与回归测试"]


def run_cli(python: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": str(PROJECT_DIR), "PATH": "", "SYSTEMROOT": "", "HOME": "", "TEMP": "", "TMP": ""}
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_DIR)
    return subprocess.run(
        [python, "-m", "sddctx.cli", *args],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        env=env,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="验证任务状态复用")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--artifacts", default=str(ARTIFACTS_DIR))
    parser.add_argument(
        "--scope-title",
        default="",
        help="PowerContext Scope 名称；默认使用一个全新的 Scope，保证「空状态起点」",
    )
    args = parser.parse_args()

    # 每次验证使用一个全新的 Scope，起点必然为空
    scope_title = args.scope_title or f"orderflow-refund-sdd-verify-{int(time.time())}"
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)

    # 1) 空状态起点
    show_before = run_cli(args.python, ["--scope-title", scope_title, "state", "show"])
    empty_before = show_before.returncode != 0 or "没有任务状态" in show_before.stdout

    # 2) 写入状态
    save = run_cli(
        args.python,
        [
            "--scope-title",
            scope_title,
            "state",
            "save",
            "--task",
            TASK,
            "--task-id",
            "TASK-REFUND-014",
            "--done",
            DONE[0],
            "--todo",
            TODO[0],
            "--todo",
            TODO[1],
        ],
    )
    if save.returncode != 0:
        print(f"[error] 写入任务状态失败：{save.stdout}\n{save.stderr}", file=sys.stderr)
        return 1

    # 3) 另一个进程读回
    show_after = run_cli(args.python, ["--scope-title", scope_title, "state", "show"])
    state: dict = {}
    if show_after.returncode == 0:
        try:
            state = json.loads(show_after.stdout)
        except json.JSONDecodeError:
            state = {}
    reused = (
        state.get("done") == DONE
        and state.get("todo") == TODO
        and state.get("task_id") == "TASK-REFUND-014"
    )

    # 4) 上下文里确实用到了状态
    context = run_cli(
        args.python,
        ["--scope-title", scope_title, "context", "--task", TASK, "--quiet"],
    )
    context_text = context.stdout
    state_used = DONE[0] in context_text and TODO[0] in context_text

    result = {
        "scope_title": scope_title,
        "empty_state_before": empty_before,
        "save_exit_code": save.returncode,
        "load_exit_code": show_after.returncode,
        "state": state,
        "reused_after_restart": reused,
        "state_used_in_context": state_used,
        "powercontext_scope": state.get("task_id", ""),
    }
    (artifacts / "state-check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (artifacts / "powercontext-state.log").write_text(
        "$ sddctx state show\n"
        f"# 退出码：{show_after.returncode}\n\n{show_after.stdout}\n{show_after.stderr}",
        encoding="utf-8",
    )

    print(f"[{'OK' if empty_before else 'FAIL'}] 空状态起点")
    print(f"[{'OK' if reused else 'FAIL'}] 重启后读回状态")
    print(f"[{'OK' if state_used else 'FAIL'}] 状态被上下文使用")
    ok = empty_before and reused and state_used
    print("✅ 状态复用检查通过" if ok else "❌ 状态复用检查未通过")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
