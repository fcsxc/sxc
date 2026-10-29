"""跑完整个验证样例，并汇总结果。

依次执行：
1. 导入工程资料到 seekdb；
2. 上下文正确性检查（必要来源齐全 + 已失效规格被排除 + 规格更新后输出随之变化）；
3. 任务状态复用检查（空状态起点 → 写入 → 跨进程读回 → 被上下文使用）；
4. 修改前失败 / 修改后通过 + 回归测试；
5. 把验证结果写回 PowerContext，并重新生成带状态的上下文包；
6. 依据真实产物生成提交材料文档。

结果写入 ``artifacts/verify-all.json``。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = PROJECT_DIR / "artifacts"
PYTHON = sys.executable


def run(args: list[str], label: str) -> tuple[bool, str]:
    print(f"\n===== {label} =====")
    completed = subprocess.run(args, cwd=str(PROJECT_DIR), capture_output=True, text=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    print(output.strip()[-4000:])
    return completed.returncode == 0, output


def main() -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    ok, _ = run([PYTHON, "-m", "sddctx.cli", "import"], "1/6 导入工程资料到 seekdb")
    results["import"] = {"ok": ok}

    ok, _ = run([PYTHON, "scripts/verify_context.py"], "2/6 上下文正确性检查")
    results["context"] = {"ok": ok}

    ok, _ = run([PYTHON, "scripts/verify_state.py"], "3/6 任务状态复用检查")
    results["state"] = {"ok": ok}

    ok, _ = run([PYTHON, "scripts/verify_before_after.py"], "4/6 修改前失败 / 修改后通过")
    results["before_after"] = {"ok": ok}

    summary_path = ARTIFACTS_DIR / "test-summary.json"
    summary = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    verifications = []
    for key, label in (
        ("before_target", "目标测试（修改前）"),
        ("after_target", "目标测试（修改后）"),
        ("after_regression", "回归测试（修改后）"),
    ):
        info = summary.get(key, {})
        if not info:
            continue
        verifications.append(
            {
                "name": label,
                "command": info.get("command", ""),
                "exit_code": info.get("exit_code"),
                "at": "",
            }
        )

    verifications_file = ARTIFACTS_DIR / "verifications.json"
    verifications_file.write_text(
        json.dumps(verifications, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok, _ = run(
        [
            PYTHON,
            "-m",
            "sddctx.cli",
            "state",
            "save",
            "--task",
            "为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：按退款原因决定运费是否可退，"
            "优惠券按 SPEC-PRICE-003 分摊，并按 SPEC-REFUND-020 把单次退款金额限制为订单实付金额的 50%。",
            "--task-id",
            "TASK-REFUND-014",
            "--done",
            "已定位 orderflow/refund.py::refundable_amount 待实现",
            "--done",
            "已实现 SPEC-REFUND-014：运费按退款原因判定可退、优惠券按 SPEC-PRICE-003 分摊、"
            "单次退款按 SPEC-REFUND-020 截断",
            "--todo",
            "运行目标测试与回归测试",
            "--verifications",
            str(verifications_file),
        ],
        "5/6 把验证结果写回 PowerContext",
    )
    results["state_write"] = {"ok": ok}

    ok, _ = run(
        [
            PYTHON,
            "-m",
            "sddctx.cli",
            "context",
            "--task",
            "为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：按退款原因决定运费是否可退，"
            "优惠券按 SPEC-PRICE-003 分摊，并按 SPEC-REFUND-020 把单次退款金额限制为订单实付金额的 50%。"
            "需要实现的符号是 orderflow.refund.refundable_amount。",
            "--out",
            str(ARTIFACTS_DIR / "context-pack.md"),
            "--log",
            str(ARTIFACTS_DIR / "context-queries.log"),
            "--quiet",
        ],
        "6/6 重新生成上下文包（含任务状态）",
    )
    results["context_pack"] = {"ok": ok}

    run([PYTHON, "scripts/gen_docs.py"], "生成提交材料文档")

    all_ok = all(item["ok"] for item in results.values())
    (ARTIFACTS_DIR / "verify-all.json").write_text(
        json.dumps({"results": results, "all_ok": all_ok}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print()
    for name, item in results.items():
        print(f"{'✅' if item['ok'] else '❌'} {name}")
    print()
    print("✅ 全部验证通过" if all_ok else "❌ 存在未通过的验证项")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
