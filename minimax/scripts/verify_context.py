"""验证验收项「上下文正确」。

检查两件事：
1. 上下文输出包含样例规定的必要来源（规格 / 代码 / 测试），且不包含已失效的规格；
2. 更新规格并重新导入后，输出使用更新后的内容（而不是固定答案）。

运行结果写入 ``artifacts/context-check.json``。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = PROJECT_DIR / "workspace"
ARTIFACTS_DIR = PROJECT_DIR / "artifacts"

TASK = (
    "为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：按退款原因决定运费是否可退，"
    "优惠券按 SPEC-PRICE-003 分摊，并按 SPEC-REFUND-020 把单次退款金额限制为订单实付金额的 50%。"
    "需要实现的符号是 orderflow.refund.refundable_amount。"
)

REQUIRED_SPECS = ["SPEC-REFUND-014", "SPEC-REFUND-020", "SPEC-PRICE-003", "SPEC-REFUND-001"]
OBSOLETE_SPEC = "SPEC-REFUND-012"
REQUIRED_SYMBOL = "orderflow/refund.py::refundable_amount"
REQUIRED_TEST_PREFIX = "tests/test_refund_quota.py::"


def main() -> int:
    parser = argparse.ArgumentParser(description="验证上下文正确性")
    parser.add_argument("--db-dir", default="")
    parser.add_argument("--database", default="sdd")
    parser.add_argument("--artifacts", default=str(ARTIFACTS_DIR))
    args = parser.parse_args()

    sys.path.insert(0, str(PROJECT_DIR))
    from sddctx import config
    from sddctx.context_pack import render_context_pack
    from sddctx.importer import load_specs
    from sddctx.seekdb_store import SeekdbStore
    from sddctx.selector import select_context

    db_dir = Path(args.db_dir) if args.db_dir else config.SEEKDB_DIR
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)

    store = SeekdbStore(db_dir, args.database)
    store.open()
    store.ensure_schema()
    try:
        pack = select_context(store, TASK)
    finally:
        store.close()

    spec_ids = [spec["spec_id"] for spec in pack.specs]
    symbol_ids = [f"{symbol['file_path']}::{symbol['name']}" for symbol in pack.symbols]
    test_ids = [f"{case['file_path']}::{case['name']}" for case in pack.tests]
    markdown = render_context_pack(pack)

    missing_specs = [spec for spec in REQUIRED_SPECS if spec not in spec_ids]
    missing_symbol = REQUIRED_SYMBOL not in symbol_ids
    missing_tests = [test for test in test_ids if False]  # 占位，真正的检查在下面
    target_tests = [test for test in test_ids if test.startswith(REQUIRED_TEST_PREFIX)]
    obsolete_in_active = OBSOLETE_SPEC in spec_ids
    obsolete_in_superseded = OBSOLETE_SPEC in [s["spec_id"] for s in pack.superseded_specs]

    # ---------------------------------------------------------- 规格变更场景
    tmp_root = Path(tempfile.mkdtemp(prefix="sddctx-specupdate-"))
    try:
        specs_copy = tmp_root / "specs"
        shutil.copytree(WORKSPACE_DIR / "specs", specs_copy)
        target = specs_copy / "SPEC-REFUND-020-refund-cap.md"
        original = target.read_text(encoding="utf-8")
        updated = original.replace("50%", "30%")
        if updated == original:
            print("[error] 规格更新脚本未能修改 SPEC-REFUND-020", file=sys.stderr)
            return 1
        target.write_text(updated, encoding="utf-8")

        update_db = tmp_root / "seekdb"
        update_store = SeekdbStore(update_db, args.database)
        update_store.open()
        update_store.ensure_schema()
        try:
            update_store.upsert_specs(load_specs(specs_copy, WORKSPACE_DIR))
            update_pack = select_context(update_store, TASK)
        finally:
            update_store.close()
        updated_spec = next(
            (spec for spec in update_pack.specs if spec["spec_id"] == "SPEC-REFUND-020"), None
        )
        update_uses_new_text = bool(updated_spec) and "30%" in updated_spec["body"]
        update_keeps_old_text = bool(updated_spec) and "50%" in updated_spec["body"]
    finally:
        # seekdb 的运行时日志可能仍被占用，清理失败不影响结论
        shutil.rmtree(tmp_root, ignore_errors=True)

    result = {
        "task": TASK,
        "selected_specs": spec_ids,
        "superseded_specs": [spec["spec_id"] for spec in pack.superseded_specs],
        "selected_symbols": symbol_ids,
        "selected_tests": test_ids,
        "checks": {
            "required_specs_present": not missing_specs,
            "missing_specs": missing_specs,
            "required_symbol_present": not missing_symbol,
            "target_tests_present": len(target_tests) >= 6,
            "target_test_count": len(target_tests),
            "obsolete_spec_excluded_from_active": not obsolete_in_active,
            "obsolete_spec_marked_superseded": obsolete_in_superseded,
            "spec_update_reflected": update_uses_new_text and not update_keeps_old_text,
        },
        "spec_update": {
            "changed": "SPEC-REFUND-020 的上限比例 50% -> 30%",
            "output_uses_updated_content": update_uses_new_text,
            "output_keeps_stale_content": update_keeps_old_text,
        },
        "queries": pack.queries,
    }
    (artifacts / "context-check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (artifacts / "context-pack.md").write_text(markdown, encoding="utf-8")
    (artifacts / "context-queries.log").write_text(
        "\n".join(f"[{q['rows']} 行] {q['sql']}" for q in pack.queries), encoding="utf-8"
    )

    checks = result["checks"]
    for name, value in checks.items():
        if name.endswith(("_present", "_excluded_from_active", "_superseded", "_reflected")):
            print(f"[{'OK' if value else 'FAIL'}] {name}: {value}")
    print(f"命中规格：{spec_ids}")
    print(f"已失效规格：{result['superseded_specs']}")
    print(f"目标测试用例数：{len(target_tests)}")
    print(f"执行 SQL 条数：{len(pack.queries)}")
    ok = (
        checks["required_specs_present"]
        and checks["required_symbol_present"]
        and checks["target_tests_present"]
        and checks["obsolete_spec_excluded_from_active"]
        and checks["obsolete_spec_marked_superseded"]
        and checks["spec_update_reflected"]
    )
    print("✅ 上下文正确性检查通过" if ok else "❌ 上下文正确性检查未通过")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
