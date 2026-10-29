"""退款额度计算。

实现状态：**待实现**（本次任务要补齐的部分）。

适用规格：
- ``SPEC-REFUND-014`` 退款额度计算规则（本文件要实现的目标）
- ``SPEC-REFUND-001`` 退款原因枚举与必填校验
- ``SPEC-REFUND-020`` 单次退款金额上限
"""

from __future__ import annotations

from .models import Order, RefundQuote, RefundRequest


def refundable_amount(order: Order, request: RefundRequest) -> RefundQuote:
    """按 ``SPEC-REFUND-014`` 计算本次退款请求的可退金额。

    待实现：需要处理退款原因校验、商品小计与优惠券分摊、运费是否可退，
    以及 ``SPEC-REFUND-020`` 规定的单次退款上限。
    """

    raise NotImplementedError("SPEC-REFUND-014 尚未实现：refundable_amount 待补齐")
