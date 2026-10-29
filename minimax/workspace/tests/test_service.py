"""回归测试：退款服务中与本次改动无关的行为。

这些用例在本次任务修改前后都必须通过。
"""

from __future__ import annotations

from conftest import ORDER_A, ORDER_B

from orderflow.models import REFUND_REASONS
from orderflow.service import RefundService


def test_get_order_returns_snapshot():
    service = RefundService({ORDER_A.order_id: ORDER_A, ORDER_B.order_id: ORDER_B})
    assert service.get_order("ORD-1001") is ORDER_A


def test_get_order_rejects_unknown_order():
    service = RefundService({ORDER_A.order_id: ORDER_A})
    try:
        service.get_order("ORD-9999")
    except KeyError as exc:
        assert "ORD-9999" in str(exc)
    else:  # pragma: no cover - 失败即说明行为被破坏
        raise AssertionError("unknown order must raise KeyError")


def test_list_refundable_reasons_matches_spec_enum():
    service = RefundService({})
    assert service.list_refundable_reasons() == REFUND_REASONS
    assert set(service.list_refundable_reasons()) == {
        "damaged",
        "quality_issue",
        "delivery_delay",
        "wrong_item",
        "other",
    }
