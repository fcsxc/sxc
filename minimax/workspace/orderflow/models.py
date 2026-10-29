"""OrderFlow 领域模型。

规格依据：
- ``SPEC-REFUND-001`` 退款原因枚举与必填校验
- ``SPEC-REFUND-014`` 退款额度计算规则
- ``SPEC-REFUND-020`` 单次退款金额上限
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

REASON_DAMAGED = "damaged"
REASON_QUALITY_ISSUE = "quality_issue"
REASON_DELIVERY_DELAY = "delivery_delay"
REASON_WRONG_ITEM = "wrong_item"
REASON_OTHER = "other"

#: ``SPEC-REFUND-001`` 规定的退款原因枚举。
REFUND_REASONS = (
    REASON_DAMAGED,
    REASON_QUALITY_ISSUE,
    REASON_DELIVERY_DELAY,
    REASON_WRONG_ITEM,
    REASON_OTHER,
)


@dataclass(frozen=True)
class LineItem:
    """订单行。金额一律使用「分」为单位的整数，避免浮点误差。"""

    sku: str
    name: str
    unit_price_cents: int
    quantity: int
    category: str = "general"


@dataclass(frozen=True)
class Order:
    """订单快照。"""

    order_id: str
    customer_id: str
    items: tuple[LineItem, ...]
    shipping_fee_cents: int = 0
    coupon_discount_cents: int = 0
    currency: str = "CNY"


@dataclass(frozen=True)
class RefundRequest:
    """一次退款申请。

    ``quantities`` 为 ``{sku: 数量}``；``requested_cents`` 为客户主动指定的
    退款金额，缺省时表示按可退上限退款。
    """

    order_id: str
    reason: str
    quantities: Mapping[str, int]
    requested_cents: int | None = None


@dataclass(frozen=True)
class RefundQuote:
    """退款额度计算结果。"""

    reason: str
    goods_refund_cents: int
    shipping_refund_cents: int
    coupon_share_cents: int
    cap_cents: int
    refundable_cents: int
    clamped: bool
