"""目标功能测试：按退款原因计算可退金额。

覆盖规格：
- ``SPEC-REFUND-014`` 退款额度计算规则（含运费可退条件）
- ``SPEC-REFUND-020`` 单次退款金额上限
- ``SPEC-REFUND-001`` 退款原因枚举与必填校验
- ``SPEC-SVC-007`` 退款单创建返回字段

本文件在本次代码修改之前会因目标行为尚未实现而失败，修改之后全部通过。
"""

from __future__ import annotations

import pytest
from conftest import ORDER_A, ORDER_B, request_for

from orderflow.models import REASON_DAMAGED, REASON_DELIVERY_DELAY, REASON_QUALITY_ISSUE
from orderflow.refund import refundable_amount
from orderflow.service import RefundService


def test_delivery_delay_refunds_shipping_fee_and_caps_at_half():
    quote = refundable_amount(
        ORDER_A,
        request_for(ORDER_A, REASON_DELIVERY_DELAY, {"SKU-1": 1}),
    )
    # 商品小计 39900 - 优惠券分摊 3342 = 36558；配送延迟可退运费 1200
    assert quote.coupon_share_cents == 3342
    assert quote.goods_refund_cents == 36558
    assert quote.shipping_refund_cents == 1200
    # 订单实付 55900，单次上限 27950
    assert quote.cap_cents == 27950
    assert quote.refundable_cents == 27950
    assert quote.clamped is True


def test_damaged_does_not_refund_shipping_fee():
    quote = refundable_amount(
        ORDER_B,
        request_for(ORDER_B, REASON_DAMAGED, {"SKU-A": 1}),
    )
    assert quote.goods_refund_cents == 5000
    assert quote.shipping_refund_cents == 0
    assert quote.coupon_share_cents == 0
    # 未触及上限
    assert quote.cap_cents == 9250
    assert quote.refundable_cents == 5000
    assert quote.clamped is False


def test_delivery_delay_refunds_shipping_fee_for_partial_refund():
    quote = refundable_amount(
        ORDER_B,
        request_for(ORDER_B, REASON_DELIVERY_DELAY, {"SKU-A": 1}),
    )
    assert quote.goods_refund_cents == 5000
    assert quote.shipping_refund_cents == 500
    assert quote.refundable_cents == 5500
    assert quote.clamped is False


def test_quality_issue_refund_is_capped_at_half_of_paid_amount():
    quote = refundable_amount(
        ORDER_B,
        request_for(ORDER_B, REASON_QUALITY_ISSUE, {"SKU-A": 2, "SKU-B": 1}),
    )
    assert quote.goods_refund_cents == 18000
    assert quote.shipping_refund_cents == 0
    assert quote.refundable_cents == 9250
    assert quote.clamped is True


def test_unknown_reason_is_rejected():
    with pytest.raises(ValueError):
        refundable_amount(
            ORDER_B,
            request_for(ORDER_B, "not_a_reason", {"SKU-A": 1}),
        )


def test_unknown_sku_is_rejected():
    with pytest.raises(ValueError):
        refundable_amount(
            ORDER_B,
            request_for(ORDER_B, REASON_DAMAGED, {"SKU-Z": 1}),
        )


def test_service_create_refund_returns_quote_fields():
    service = RefundService({ORDER_B.order_id: ORDER_B})
    result = service.create_refund(
        request_for(ORDER_B, REASON_DELIVERY_DELAY, {"SKU-A": 1})
    )
    assert result["order_id"] == "ORD-1002"
    assert result["status"] == "ACCEPTED"
    assert result["refund_cents"] == 5500
    assert result["goods_refund_cents"] == 5000
    assert result["shipping_refund_cents"] == 500
    assert result["clamped"] is False


def test_service_clamps_requested_amount_to_refundable():
    service = RefundService({ORDER_B.order_id: ORDER_B})
    result = service.create_refund(
        request_for(ORDER_B, REASON_DAMAGED, {"SKU-A": 2, "SKU-B": 1}, requested_cents=999999)
    )
    assert result["refund_cents"] == 9250
    assert result["clamped"] is True
