"""退款额度计算。

适用规格：
- ``SPEC-REFUND-014`` 退款额度计算规则（本文件实现的目标）
- ``SPEC-REFUND-001`` 退款原因枚举与必填校验
- ``SPEC-REFUND-020`` 单次退款金额上限
- ``SPEC-PRICE-003`` 优惠券按商品小计比例分摊（由 ``orderflow.pricing`` 提供）

实现要点：
1. 退款原因必须属于 ``SPEC-REFUND-001`` 的枚举，否则拒绝；
2. 可退商品金额 = 退款商品小计 − 分摊到这些商品的优惠券抵扣；
3. 运费仅在 ``delivery_delay``（配送延迟）时可退，其余原因运费不可退
   （``SPEC-REFUND-012``「运费一律不退」已被 ``SPEC-REFUND-014`` 取代）；
4. 可退金额受 ``SPEC-REFUND-020`` 的单次上限约束，超出时截断并标记 ``clamped``。
"""

from __future__ import annotations

from .models import REFUND_REASONS, REASON_DELIVERY_DELAY, Order, RefundQuote, RefundRequest
from .pricing import coupon_share_cents, refund_cap_cents


def refundable_amount(order: Order, request: RefundRequest) -> RefundQuote:
    """按 ``SPEC-REFUND-014`` 计算本次退款请求的可退金额。

    Args:
        order: 订单快照。
        request: 退款申请，含退款原因与各 SKU 的退款数量。

    Returns:
        可退额度明细（商品 / 运费 / 优惠券分摊 / 上限 / 是否被截断）。

    Raises:
        ValueError: 退款原因不在枚举内，或退款数量里出现订单中不存在的 SKU。
    """

    # SPEC-REFUND-001：退款原因必填且必须属于枚举
    if request.reason not in REFUND_REASONS:
        raise ValueError(f"invalid refund reason: {request.reason}")

    known_skus = {item.sku for item in order.items}
    unknown_skus = sorted(sku for sku in request.quantities if sku not in known_skus)
    if unknown_skus:
        raise ValueError(f"sku not in order {order.order_id}: {', '.join(unknown_skus)}")

    # SPEC-REFUND-014：可退商品金额 = 退款商品小计 − 分摊到这些商品的优惠券抵扣
    gross_goods_cents = 0
    coupon_share = 0
    for item in order.items:
        quantity = request.quantities.get(item.sku)
        if not quantity:
            continue
        gross_goods_cents += item.unit_price_cents * quantity
        coupon_share += coupon_share_cents(order, item.sku, quantity)
    goods_refund_cents = gross_goods_cents - coupon_share

    # SPEC-REFUND-014：运费仅在配送延迟时可退
    if request.reason == REASON_DELIVERY_DELAY:
        shipping_refund_cents = order.shipping_fee_cents
    else:
        shipping_refund_cents = 0

    # SPEC-REFUND-020：单次退款金额不得超过订单实付金额的 50%
    cap_cents = refund_cap_cents(order)
    refundable_before_cap = goods_refund_cents + shipping_refund_cents
    clamped = refundable_before_cap > cap_cents
    refundable_cents = cap_cents if clamped else refundable_before_cap

    return RefundQuote(
        reason=request.reason,
        goods_refund_cents=goods_refund_cents,
        shipping_refund_cents=shipping_refund_cents,
        coupon_share_cents=coupon_share,
        cap_cents=cap_cents,
        refundable_cents=refundable_cents,
        clamped=clamped,
    )
