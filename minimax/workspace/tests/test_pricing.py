"""回归测试：订单金额计算。

这些用例在本次任务修改前后都必须通过（``SPEC-PRICE-003`` / ``SPEC-REFUND-020``）。
"""

from __future__ import annotations

from conftest import ORDER_A, ORDER_B

from orderflow.pricing import (
    coupon_share_cents,
    order_subtotal_cents,
    order_total_cents,
    refund_cap_cents,
)


def test_order_subtotal_sums_line_amounts():
    assert order_subtotal_cents(ORDER_A) == 39900 + 9900 * 2
    assert order_subtotal_cents(ORDER_B) == 5000 * 2 + 8000


def test_order_total_deducts_coupon_and_adds_shipping():
    assert order_total_cents(ORDER_A) == 59700 - 5000 + 1200
    assert order_total_cents(ORDER_B) == 18000 + 500


def test_coupon_share_is_allocated_by_subtotal_ratio():
    # 5000 * 39900 / 59700 = 3341.71… -> 3342
    assert coupon_share_cents(ORDER_A, "SKU-1", 1) == 3342
    # 5000 * 9900 * 2 / 59700 = 1658.29… -> 1658
    assert coupon_share_cents(ORDER_A, "SKU-2", 2) == 1658


def test_coupon_share_is_zero_without_discount():
    assert coupon_share_cents(ORDER_B, "SKU-A", 1) == 0


def test_refund_cap_is_half_of_paid_amount():
    assert refund_cap_cents(ORDER_A) == 55900 // 2
    assert refund_cap_cents(ORDER_B) == 18500 // 2
