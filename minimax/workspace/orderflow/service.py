"""OrderFlow 退款服务。

规格依据：
- ``SPEC-SVC-007`` 退款单创建返回字段
- ``SPEC-REFUND-001`` 退款原因枚举与必填校验
"""

from __future__ import annotations

from .models import REFUND_REASONS, Order, RefundRequest
from .refund import refundable_amount


class RefundService:
    """退款服务：受理退款申请并返回可退额度。"""

    def __init__(self, orders: dict[str, Order]) -> None:
        self._orders = dict(orders)

    def get_order(self, order_id: str) -> Order:
        """按订单号取订单快照。"""

        try:
            return self._orders[order_id]
        except KeyError as exc:  # pragma: no cover - 统一错误语义
            raise KeyError(f"order not found: {order_id}") from exc

    def list_refundable_reasons(self) -> tuple[str, ...]:
        """可受理的退款原因（``SPEC-REFUND-001``）。"""

        return REFUND_REASONS

    def create_refund(self, request: RefundRequest) -> dict:
        """受理退款申请。

        返回字段遵循 ``SPEC-SVC-007``；金额部分依赖 ``refundable_amount``。
        """

        order = self.get_order(request.order_id)
        quote = refundable_amount(order, request)
        if request.requested_cents is None:
            amount = quote.refundable_cents
        else:
            amount = min(request.requested_cents, quote.refundable_cents)
        return {
            "order_id": request.order_id,
            "reason": request.reason,
            "status": "ACCEPTED",
            "refund_cents": amount,
            "goods_refund_cents": quote.goods_refund_cents,
            "shipping_refund_cents": quote.shipping_refund_cents,
            "coupon_share_cents": quote.coupon_share_cents,
            "cap_cents": quote.cap_cents,
            "clamped": quote.clamped,
        }
