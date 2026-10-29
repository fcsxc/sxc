"""退款额度计算。

适用规格：
- ``SPEC-REFUND-014`` 退款额度计算规则
- ``SPEC-REFUND-001`` 退款原因枚举与必填校验
- ``SPEC-REFUND-020`` 单次退款金额上限
"""

from __future__ import annotations

from .models import (
    REASON_DELIVERY_DELAY,
    REFUND_REASONS,
    Order,
    RefundQuote,
    RefundRequest,
)
from .pricing import coupon_share_cents, refund_cap_cents


def refundable_amount(order: Order, request: RefundRequest) -> RefundQuote:
    """按 ``SPEC-REFUND-014`` 计算本次退款请求的可退金额。"""

    if request.reason not in REFUND_REASONS:
        raise ValueError(f"unknown refund reason: {request.reason}")

    goods_subtotal_cents = 0
    coupon_share_total_cents = 0

    for sku, quantity in request.quantities.items():
        matching_items = [item for item in order.items if item.sku == sku]
        if not matching_items:
            raise ValueError(f"sku {sku!r} does not belong to order {order.order_id}")
        if quantity < 0:
            raise ValueError(f"refund quantity cannot be negative for sku {sku!r}")

        ordered_quantity = sum(item.quantity for item in matching_items)
        if quantity > ordered_quantity:
            raise ValueError(f"refund quantity exceeds ordered quantity for sku {sku!r}")

        remaining = quantity
        for item in matching_items:
            refunded_quantity = min(remaining, item.quantity)
            goods_subtotal_cents += item.unit_price_cents * refunded_quantity
            remaining -= refunded_quantity

        coupon_share_total_cents += coupon_share_cents(order, sku, quantity)

    goods_refund_cents = goods_subtotal_cents - coupon_share_total_cents
    shipping_refund_cents = (
        order.shipping_fee_cents if request.reason == REASON_DELIVERY_DELAY else 0
    )

    refundable_before_cap = goods_refund_cents + shipping_refund_cents
    cap_cents = refund_cap_cents(order)
    clamped = refundable_before_cap > cap_cents
    refundable_cents = min(refundable_before_cap, cap_cents)

    return RefundQuote(
        reason=request.reason,
        goods_refund_cents=goods_refund_cents,
        shipping_refund_cents=shipping_refund_cents,
        coupon_share_cents=coupon_share_total_cents,
        cap_cents=cap_cents,
        refundable_cents=refundable_cents,
        clamped=clamped,
    )
