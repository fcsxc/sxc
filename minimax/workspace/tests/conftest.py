"""共享测试夹具：订单样本与退款请求构造。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orderflow.models import LineItem, Order, RefundRequest  # noqa: E402

#: 含运费与优惠券的订单：用于验证优惠券分摊与运费可退规则。
ORDER_A = Order(
    order_id="ORD-1001",
    customer_id="CUST-1",
    items=(
        LineItem("SKU-1", "机械键盘", 39900, 1, "peripheral"),
        LineItem("SKU-2", "鼠标垫", 9900, 2, "accessory"),
    ),
    shipping_fee_cents=1200,
    coupon_discount_cents=5000,
)

#: 多商品、无优惠券的订单：用于验证部分退款与退款上限。
ORDER_B = Order(
    order_id="ORD-1002",
    customer_id="CUST-2",
    items=(
        LineItem("SKU-A", "显示器支架", 5000, 2, "peripheral"),
        LineItem("SKU-B", "USB 扩展坞", 8000, 1, "peripheral"),
    ),
    shipping_fee_cents=500,
    coupon_discount_cents=0,
)


def request_for(order: Order, reason: str, quantities: dict[str, int], requested_cents: int | None = None) -> RefundRequest:
    """构造一次退款申请。"""

    return RefundRequest(
        order_id=order.order_id,
        reason=reason,
        quantities=quantities,
        requested_cents=requested_cents,
    )
