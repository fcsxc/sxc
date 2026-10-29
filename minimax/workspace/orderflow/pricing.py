"""订单金额计算。

规格依据：
- ``SPEC-PRICE-003`` 订单实付金额与优惠券分摊
- ``SPEC-REFUND-020`` 单次退款金额上限（订单实付金额的 50%，向下取整）
"""

from __future__ import annotations

from .models import Order

#: ``SPEC-REFUND-020``：单次退款上限为订单实付金额的 1/2。
REFUND_CAP_NUMERATOR = 1
REFUND_CAP_DENOMINATOR = 2


def order_subtotal_cents(order: Order) -> int:
    """商品小计（不含运费，不扣优惠券）。"""

    return sum(item.unit_price_cents * item.quantity for item in order.items)


def order_total_cents(order: Order) -> int:
    """订单实付金额 = 商品小计 − 优惠券抵扣 + 运费。"""

    return order_subtotal_cents(order) - order.coupon_discount_cents + order.shipping_fee_cents


def _ratio_round(numerator: int, denominator: int) -> int:
    """整数四舍五入（分母为正时）。"""

    if denominator <= 0:
        return 0
    return (numerator + denominator // 2) // denominator


def coupon_share_cents(order: Order, sku: str, quantity: int) -> int:
    """按商品小计比例分摊到 ``sku`` 的优惠券抵扣（``SPEC-PRICE-003``）。

    分摊结果四舍五入到分，且不超过该行本身的金额。
    """

    subtotal = order_subtotal_cents(order)
    if subtotal <= 0 or order.coupon_discount_cents <= 0 or quantity <= 0:
        return 0
    share = 0
    for item in order.items:
        if item.sku != sku:
            continue
        line_amount = item.unit_price_cents * quantity
        allocated = _ratio_round(order.coupon_discount_cents * line_amount, subtotal)
        share += min(allocated, line_amount)
    return share


def refund_cap_cents(order: Order) -> int:
    """单次退款金额上限（``SPEC-REFUND-020``），向下取整到分。"""

    total = order_total_cents(order)
    return total * REFUND_CAP_NUMERATOR // REFUND_CAP_DENOMINATOR
