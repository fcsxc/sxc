# 开发上下文包

- 任务：为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：按退款原因决定运费是否可退，优惠券按 SPEC-PRICE-003 分摊，并按 SPEC-REFUND-020 把单次退款金额限制为订单实付金额的 50%。需要实现的符号是 orderflow.refund.refundable_amount。
- 生成时间：2026-10-30T02:29:03
- 规格与代码来源：seekdb 嵌入式实例
- 焦点模块：orderflow.refund, orderflow.pricing, orderflow.service

## 1. 本次任务适用的规格条目

### SPEC-REFUND-020 单次退款金额上限为订单实付金额的 50%（来源：`specs/SPEC-REFUND-020-refund-cap.md`，状态：active，版本：rev1，相关度：40.158）

## 规则

1. 单次退款金额不得超过订单实付金额的 50%。
2. 订单实付金额 = 商品小计 − 优惠券抵扣 + 运费。
3. 上限向下取整到分。
4. 可退金额超过上限时按上限截断，并在结果中标记 `clamped`。

## 变更说明

本条目在 2026-10 评审前由「单次退款上限为订单实付金额的 30%」调整为 50%。
上下文模块每次都从数据库读取最新条目内容，不得缓存旧数值。

- 适用模块：orderflow.pricing, orderflow.refund

### SPEC-REFUND-014 退款额度计算规则（来源：`specs/SPEC-REFUND-014-refund-quota.md`，状态：active，版本：rev1，相关度：32.47）

## 规则

1. 可退商品金额 = 退款商品小计 − 分摊到这些商品的优惠券抵扣。退款商品小计按 `单价 × 数量` 计算。
2. 优惠券抵扣按商品小计比例分摊，分摊结果四舍五入到分（见 `SPEC-PRICE-003`）。
3. 运费可退条件：仅当 `reason == "delivery_delay"`（配送延迟）时运费全额可退；其余原因运费不可退，`shipping_refund_cents` 为 0。
4. 可退金额 = 可退商品金额 + 可退运费，并受 `SPEC-REFUND-020` 的单次上限约束。
5. 当可退金额被上限截断时，`clamped` 必须为 `True`。
6. 退款商品必须属于该订单；未知 SKU 必须拒绝并抛出 `ValueError`。

## 失效的旧规则

`SPEC-REFUND-012`（运费一律不退）已被本条目取代，不得继续作为约束。

## 验收

- `damaged` 订单中运费不可退，`delivery_delay` 订单中运费可退。
- 超过上限时 `refundable_cents` 等于上限且 `clamped` 为 `True`。

- 适用模块：orderflow.refund
- 取代：SPEC-REFUND-012

### SPEC-PRICE-003 订单实付金额与优惠券分摊（来源：`specs/SPEC-PRICE-003-coupon-allocation.md`，状态：active，版本：rev1，相关度：30.052）

## 规则

1. 所有金额一律使用「分」为单位的整数，不使用浮点数。
2. 商品小计 = 各行 `单价 × 数量` 之和。
3. 订单实付金额 = 商品小计 − 优惠券抵扣 + 运费。
4. 优惠券抵扣按退款涉及商品的金额占商品小计的比例分摊，分摊结果四舍五入到分，且不超过该行金额。
5. 分摊使用整数运算实现：`(numerator + denominator // 2) // denominator`。

## 验收

- `SPEC-PRICE-003` 相关回归用例在本次改动前后均须通过。

- 适用模块：orderflow.pricing

### SPEC-REFUND-001 退款原因枚举与必填校验（来源：`specs/SPEC-REFUND-001-refund-reason.md`，状态：active，版本：rev1，相关度：14.566）

## 规则

1. 退款申请必须携带 `reason` 字段，取值必须属于退款原因枚举。
2. 退款原因枚举为：`damaged`（商品损坏）、`quality_issue`（质量问题）、`delivery_delay`（配送延迟）、`wrong_item`（错发商品）、`other`（其他）。
3. 原因不在枚举内时必须拒绝请求并抛出 `ValueError`，不得静默降级为 `other`。
4. 原因枚举由 `orderflow.models.REFUND_REASONS` 暴露，服务层通过 `RefundService.list_refundable_reasons()` 返回。

## 验收

- 传入 `not_a_reason` 时 `refundable_amount` 抛出 `ValueError`。
- 合法原因不抛出异常。

- 适用模块：orderflow.refund, orderflow.service

### 已失效的决策（仅供追溯，**不得**作为约束）

- `SPEC-REFUND-012` 运费一律不予退款（来源：`specs/SPEC-REFUND-012-shipping-never-refunded.md`，状态：superseded）

## 2. 需要修改的代码文件与符号

### `orderflow/refund.py` :: `refundable_amount`（function，第 23-77 行，模块 `orderflow.refund`，相关度：27.5）

按 ``SPEC-REFUND-014`` 计算本次退款请求的可退金额。

Args:
    order: 订单快照。
    request: 退款申请，含退款原因与各 SKU 的退款数量。

Returns:
    可退额度明细（商品 / 运费 / 优惠券分摊 / 上限 / 是否被截断）。

Raises:
    ValueError: 退款原因不在枚举内，或退款数量里出现订单中不存在的 SKU。

```python
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
```

### `orderflow/pricing.py` :: `order_total_cents`（function，第 23-26 行，模块 `orderflow.pricing`，相关度：13.5）

订单实付金额 = 商品小计 − 优惠券抵扣 + 运费。

```python
def order_total_cents(order: Order) -> int:
    """订单实付金额 = 商品小计 − 优惠券抵扣 + 运费。"""

    return order_subtotal_cents(order) - order.coupon_discount_cents + order.shipping_fee_cents
```

### `orderflow/pricing.py` :: `coupon_share_cents`（function，第 37-53 行，模块 `orderflow.pricing`，相关度：12.5）

按商品小计比例分摊到 ``sku`` 的优惠券抵扣（``SPEC-PRICE-003``）。

分摊结果四舍五入到分，且不超过该行本身的金额。

```python
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
```

### `orderflow/pricing.py` :: `refund_cap_cents`（function，第 56-60 行，模块 `orderflow.pricing`，相关度：12.5）

单次退款金额上限（``SPEC-REFUND-020``），向下取整到分。

```python
def refund_cap_cents(order: Order) -> int:
    """单次退款金额上限（``SPEC-REFUND-020``），向下取整到分。"""

    total = order_total_cents(order)
    return total * REFUND_CAP_NUMERATOR // REFUND_CAP_DENOMINATOR
```

### `orderflow/service.py` :: `list_refundable_reasons`（method，第 28-31 行，模块 `orderflow.service`，相关度：11.0）

可受理的退款原因（``SPEC-REFUND-001``）。

```python
    def list_refundable_reasons(self) -> tuple[str, ...]:
        """可受理的退款原因（``SPEC-REFUND-001``）。"""

        return REFUND_REASONS
```

### `orderflow/service.py` :: `create_refund`（method，第 33-55 行，模块 `orderflow.service`，相关度：10.0）

受理退款申请。

返回字段遵循 ``SPEC-SVC-007``；金额部分依赖 ``refundable_amount``。

```python
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
```

### `orderflow/models.py` :: `RefundRequest`（class，第 54-64 行，模块 `orderflow.models`，相关度：8.5）

一次退款申请。

``quantities`` 为 ``{sku: 数量}``；``requested_cents`` 为客户主动指定的
退款金额，缺省时表示按可退上限退款。

```python
class RefundRequest:
    """一次退款申请。

    ``quantities`` 为 ``{sku: 数量}``；``requested_cents`` 为客户主动指定的
    退款金额，缺省时表示按可退上限退款。
    """

    order_id: str
    reason: str
    quantities: Mapping[str, int]
    requested_cents: int | None = None
```

### `orderflow/pricing.py` :: `order_subtotal_cents`（function，第 17-20 行，模块 `orderflow.pricing`，相关度：8.5）

商品小计（不含运费，不扣优惠券）。

```python
def order_subtotal_cents(order: Order) -> int:
    """商品小计（不含运费，不扣优惠券）。"""

    return sum(item.unit_price_cents * item.quantity for item in order.items)
```

### `orderflow/service.py` :: `RefundService`（class，第 14-55 行，模块 `orderflow.service`，相关度：8.5）

退款服务：受理退款申请并返回可退额度。

```python
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
```

### `orderflow/models.py` :: `Order`（class，第 42-50 行，模块 `orderflow.models`，相关度：7.5）

订单快照。

```python
class Order:
    """订单快照。"""

    order_id: str
    customer_id: str
    items: tuple[LineItem, ...]
    shipping_fee_cents: int = 0
    coupon_discount_cents: int = 0
    currency: str = "CNY"
```

### `orderflow/pricing.py` :: `_ratio_round`（function，第 29-34 行，模块 `orderflow.pricing`，相关度：6.5）

整数四舍五入（分母为正时）。

```python
def _ratio_round(numerator: int, denominator: int) -> int:
    """整数四舍五入（分母为正时）。"""

    if denominator <= 0:
        return 0
    return (numerator + denominator // 2) // denominator
```

### `orderflow/service.py` :: `get_order`（method，第 20-26 行，模块 `orderflow.service`，相关度：6.0）

按订单号取订单快照。

```python
    def get_order(self, order_id: str) -> Order:
        """按订单号取订单快照。"""

        try:
            return self._orders[order_id]
        except KeyError as exc:  # pragma: no cover - 统一错误语义
            raise KeyError(f"order not found: {order_id}") from exc
```

### `orderflow/service.py` :: `__init__`（method，第 17-18 行，模块 `orderflow.service`，相关度：5.0）

```python
    def __init__(self, orders: dict[str, Order]) -> None:
        self._orders = dict(orders)
```

### `orderflow/models.py` :: `LineItem`（class，第 31-38 行，模块 `orderflow.models`，相关度：4.5）

订单行。金额一律使用「分」为单位的整数，避免浮点误差。

```python
class LineItem:
    """订单行。金额一律使用「分」为单位的整数，避免浮点误差。"""

    sku: str
    name: str
    unit_price_cents: int
    quantity: int
    category: str = "general"
```

## 3. 用于验证功能与兼容性的测试

### `tests/test_service.py` :: `test_list_refundable_reasons_matches_spec_enum`（被测模块：orderflow.models, orderflow.service，相关度：7.0）

断言要点：

```python
assert service.list_refundable_reasons() == REFUND_REASONS; assert set(service.list_refundable_reasons()) == {
```

### `tests/test_pricing.py` :: `test_refund_cap_is_half_of_paid_amount`（被测模块：orderflow.pricing，相关度：6.0）

断言要点：

```python
assert refund_cap_cents(ORDER_A) == 55900 // 2; assert refund_cap_cents(ORDER_B) == 18500 // 2
```

### `tests/test_refund_quota.py` :: `test_damaged_does_not_refund_shipping_fee`（被测模块：orderflow.models, orderflow.refund, orderflow.service，相关度：6.0）

断言要点：

```python
assert quote.goods_refund_cents == 5000; assert quote.shipping_refund_cents == 0; assert quote.coupon_share_cents == 0; assert quote.cap_cents == 9250; assert quote.refundable_cents == 5000; assert quote.clamped is False
```

### `tests/test_refund_quota.py` :: `test_delivery_delay_refunds_shipping_fee_and_caps_at_half`（被测模块：orderflow.models, orderflow.refund, orderflow.service，相关度：6.0）

断言要点：

```python
assert quote.coupon_share_cents == 3342; assert quote.goods_refund_cents == 36558; assert quote.shipping_refund_cents == 1200; assert quote.cap_cents == 27950; assert quote.refundable_cents == 27950; assert quote.clamped is True
```

### `tests/test_refund_quota.py` :: `test_delivery_delay_refunds_shipping_fee_for_partial_refund`（被测模块：orderflow.models, orderflow.refund, orderflow.service，相关度：6.0）

断言要点：

```python
assert quote.goods_refund_cents == 5000; assert quote.shipping_refund_cents == 500; assert quote.refundable_cents == 5500; assert quote.clamped is False
```

### `tests/test_refund_quota.py` :: `test_quality_issue_refund_is_capped_at_half_of_paid_amount`（被测模块：orderflow.models, orderflow.refund, orderflow.service，相关度：6.0）

断言要点：

```python
assert quote.goods_refund_cents == 18000; assert quote.shipping_refund_cents == 0; assert quote.refundable_cents == 9250; assert quote.clamped is True
```

### `tests/test_refund_quota.py` :: `test_service_clamps_requested_amount_to_refundable`（被测模块：orderflow.models, orderflow.refund, orderflow.service，相关度：6.0）

断言要点：

```python
assert result["refund_cents"] == 9250; assert result["clamped"] is True
```

### `tests/test_refund_quota.py` :: `test_service_create_refund_returns_quote_fields`（被测模块：orderflow.models, orderflow.refund, orderflow.service，相关度：6.0）

断言要点：

```python
assert result["order_id"] == "ORD-1002"; assert result["status"] == "ACCEPTED"; assert result["refund_cents"] == 5500; assert result["goods_refund_cents"] == 5000; assert result["shipping_refund_cents"] == 500; assert result["clamped"] is False
```

### `tests/test_pricing.py` :: `test_coupon_share_is_allocated_by_subtotal_ratio`（被测模块：orderflow.pricing，相关度：5.0）

断言要点：

```python
assert coupon_share_cents(ORDER_A, "SKU-1", 1) == 3342; assert coupon_share_cents(ORDER_A, "SKU-2", 2) == 1658
```

### `tests/test_pricing.py` :: `test_coupon_share_is_zero_without_discount`（被测模块：orderflow.pricing，相关度：5.0）

断言要点：

```python
assert coupon_share_cents(ORDER_B, "SKU-A", 1) == 0
```

### `tests/test_pricing.py` :: `test_order_subtotal_sums_line_amounts`（被测模块：orderflow.pricing，相关度：5.0）

断言要点：

```python
assert order_subtotal_cents(ORDER_A) == 39900 + 9900 * 2; assert order_subtotal_cents(ORDER_B) == 5000 * 2 + 8000
```

### `tests/test_pricing.py` :: `test_order_total_deducts_coupon_and_adds_shipping`（被测模块：orderflow.pricing，相关度：5.0）

断言要点：

```python
assert order_total_cents(ORDER_A) == 59700 - 5000 + 1200; assert order_total_cents(ORDER_B) == 18000 + 500
```

## 4. 已完成事项、待办事项与已有验证结果

- 任务标识：`TASK-REFUND-014`
- 状态更新时间：2026-10-30T02:29:00
- 上下文指纹：``

### 已完成

- 已定位 orderflow/refund.py::refundable_amount 待实现
- 已实现 SPEC-REFUND-014：运费按退款原因判定可退、优惠券按 SPEC-PRICE-003 分摊、单次退款按 SPEC-REFUND-020 截断

### 待办

- 运行目标测试与回归测试

### 已有验证结果

- 目标测试（修改后）：命令 `python -m pytest -q tests/test_refund_quota.py`，退出码 0，时间 
- 回归测试（修改后）：命令 `python -m pytest -q tests/test_pricing.py tests/test_service.py`，退出码 0，时间 
