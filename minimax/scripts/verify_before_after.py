"""复现验收项「代码修改有效」：同一组目标测试，修改前失败、修改后通过。

做法：
1. 把 ``workspace/`` 复制到临时目录；
2. 用 ``snapshots/before/`` 中的修改前代码覆盖 ``orderflow/refund.py``；
3. 运行目标功能测试 -> 期望失败（且失败原因是功能未实现，而非环境错误）；
4. 换回修改后的代码 -> 运行目标测试与相关回归测试 -> 期望全部通过。

运行日志写入 ``artifacts/test-before.log`` 与 ``artifacts/test-after.log``。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = PROJECT_DIR / "workspace"
SNAPSHOT_DIR = PROJECT_DIR / "snapshots" / "before"
ARTIFACTS_DIR = PROJECT_DIR / "artifacts"

TARGET_TESTS = ["tests/test_refund_quota.py"]
REGRESSION_TESTS = ["tests/test_pricing.py", "tests/test_service.py"]


def run_pytest(cwd: Path, targets: list[str], python: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [python, "-m", "pytest", "-q", *targets],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="复现修改前失败 / 修改后通过")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--artifacts", default=str(ARTIFACTS_DIR))
    args = parser.parse_args()

    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="sddctx-beforeafter-") as tmp:
        cwd = Path(tmp) / "workspace"
        shutil.copytree(WORKSPACE_DIR, cwd)

        # ---------------------------------------------------------- 修改前
        for relative in ["orderflow/refund.py"]:
            snapshot = SNAPSHOT_DIR / relative
            if not snapshot.exists():
                print(f"[error] 缺少修改前快照：{snapshot}", file=sys.stderr)
                return 2
            shutil.copy2(snapshot, cwd / relative)

        before = run_pytest(cwd, TARGET_TESTS, args.python)
        (artifacts / "test-before.log").write_text(
            f"$ python -m pytest -q {' '.join(TARGET_TESTS)}\n"
            f"# 修改前代码：snapshots/before/\n"
            f"# 退出码：{before.returncode}\n\n{before.stdout}\n{before.stderr}",
            encoding="utf-8",
        )
        print(f"[修改前] 目标测试退出码 = {before.returncode}（期望非 0）")
        if before.returncode == 0:
            print("[error] 修改前目标测试竟然通过了，验收不成立", file=sys.stderr)
            return 1
        if "NotImplementedError" not in (before.stdout + before.stderr):
            print(
                "[error] 修改前的失败原因不是「目标行为未实现」，而是环境/依赖问题",
                file=sys.stderr,
            )
            return 1

        # ---------------------------------------------------------- 修改后
        for relative in ["orderflow/refund.py"]:
            shutil.copy2(WORKSPACE_DIR / relative, cwd / relative)

        after_target = run_pytest(cwd, TARGET_TESTS, args.python)
        after_regression = run_pytest(cwd, REGRESSION_TESTS, args.python)
        (artifacts / "test-after.log").write_text(
            f"$ python -m pytest -q {' '.join(TARGET_TESTS)}\n"
            f"# 修改后代码：workspace/\n"
            f"# 退出码：{after_target.returncode}\n\n{after_target.stdout}\n{after_target.stderr}\n\n"
            f"$ python -m pytest -q {' '.join(REGRESSION_TESTS)}\n"
            f"# 退出码：{after_regression.returncode}\n\n{after_regression.stdout}\n{after_regression.stderr}",
            encoding="utf-8",
        )
        print(f"[修改后] 目标测试退出码 = {after_target.returncode}（期望 0）")
        print(f"[修改后] 回归测试退出码 = {after_regression.returncode}（期望 0）")

        summary = {
            "before": {
                "command": f"python -m pytest -q {' '.join(TARGET_TESTS)}",
                "exit_code": before.returncode,
                "failure_reason": "NotImplementedError（目标行为未实现）",
            },
            "after_target": {
                "command": f"python -m pytest -q {' '.join(TARGET_TESTS)}",
                "exit_code": after_target.returncode,
            },
            "after_regression": {
                "command": f"python -m pytest -q {' '.join(REGRESSION_TESTS)}",
                "exit_code": after_regression.returncode,
            },
        }
        (artifacts / "test-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if after_target.returncode != 0 or after_regression.returncode != 0:
        return 1
    print("✅ 修改前失败 / 修改后通过，回归测试全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
