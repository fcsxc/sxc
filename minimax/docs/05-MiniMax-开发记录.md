# MiniMax 开发记录

本文件记录 **MiniMax 在本次任务中的实际参与**：任务是什么、模块提供了哪些上下文、模型据此做了什么修改、修改结果如何。

## 一、提交实现由谁产出

- **提交的最终实现**：由 **MiniMax Code（模型 MiniMax-M3.1-Flash）** 在本次开发会话中，依据上下文模块产出的上下文包完成；
- **模块内置的 MiniMax API 接入路径**（`sddctx agent apply`）：真实可复现，本机已跑过多轮，完整记录见 [`../artifacts/minimax-api-attempts.md`](`../artifacts/minimax-api-attempts.md`)；
- 两者使用**同一份上下文包**（同一条 `sddctx context` 产出），因此上下文模块对二者的作用完全一致。

## 二、本次开发会话记录

# MiniMax 开发记录（本次会话）

> 本文件记录 **MiniMax Code（模型 MiniMax-M3.1-Flash）** 在本次任务中的实际参与过程：
> 任务是什么、上下文模块提供了什么、MiniMax 据此做了什么修改、结果如何。
> 与提交的代码差异（`docs/06-代码差异.md`）逐行对应。

---

## 一、收到的任务

来自赛题《规有所依——面向软件持续演进的 SDD 上下文管理系统》（MiniMax × OceanBase 赛道，20 分）：

> 为已有 AI 开发助手实现或改进工程上下文模块，根据开发任务提供当前有效的规格、相关代码和测试，
> 并通过实际代码修改验证效果。

技术要求：使用 **MiniMax** 参与代码修改；使用 **seekdb 或 OceanBase** 存储、检索工程资料；
使用 **PowerContext** 保存并复用任务状态。

由本作品定义的开发任务：

> 为 OrderFlow 的 `orderflow.refund` 模块实现 `SPEC-REFUND-014`：按退款原因决定运费是否可退，
> 优惠券按 `SPEC-PRICE-003` 分摊，并按 `SPEC-REFUND-020` 把单次退款金额限制为订单实付金额的 50%。
> 需要实现的符号是 `orderflow.refund.refundable_amount`。

---

## 二、上下文模块先给出上下文（MiniMax 才开始动手）

在写任何代码之前，先让上下文模块产出上下文包——**没有这一步，MiniMax 就是在盲写**。

```bash
$ python -m sddctx.cli import
规格条目 9 条，代码符号 32 个，测试用例 16 个
seekdb 统计：{'spec_item': 9, 'code_symbol': 32, 'test_case': 16}

$ python -m sddctx.cli context --task "为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：…" \
      --out artifacts/context-pack.md
```

上下文包给出了四类信息（完整内容见 `artifacts/context-pack.md`）：

1. **适用的规格条目**：`SPEC-REFUND-014`、`SPEC-REFUND-020`、`SPEC-PRICE-003`、`SPEC-REFUND-001`，
   并附带正文与来源文件路径；
2. **已失效的决策**：`SPEC-REFUND-012`「运费一律不退」已被 `SPEC-REFUND-014` 取代，
   上下文明确标注**不得**作为约束——这条避免了把旧规则写进实现；
3. **需要修改的代码**：`orderflow/refund.py::refundable_amount`（当前是抛
   `NotImplementedError` 的桩），以及只读参考 `orderflow/pricing.py` 的
   `order_subtotal_cents` / `order_total_cents` / `coupon_share_cents` / `refund_cap_cents`
   与 `orderflow/models.py` 的 `Order` / `RefundRequest` / `RefundQuote` / `REFUND_REASONS`；
4. **测试**：目标功能测试 `tests/test_refund_quota.py` 的 8 个用例（含断言要点），
   回归测试 `tests/test_pricing.py` / `tests/test_service.py`。

以上规格、代码、测试全部来自 **seekdb 的真实 SQL 查询**（`artifacts/context-queries.log` 共 12 条，
含 `MATCH(search_text) AGAINST(...)` 全文检索），任务状态来自 **PowerContext**。

---

## 三、MiniMax 的修改过程

### 3.1 依据规格确定实现规则

MiniMax 从上下文里提取出四条必须满足的规则：

| 规则 | 来源 |
| --- | --- |
| 退款原因必须属于 `REFUND_REASONS`，否则 `ValueError` | `SPEC-REFUND-001` |
| 可退商品金额 = 退款商品小计 − 分摊的优惠券抵扣 | `SPEC-REFUND-014` + `SPEC-PRICE-003` |
| 运费仅在 `delivery_delay` 时可退，其余原因不可退 | `SPEC-REFUND-014`（取代 `SPEC-REFUND-012`） |
| 单次退款上限 = 订单实付金额的 50%，超出则截断并标记 `clamped` | `SPEC-REFUND-020` |

### 3.2 复用既有函数，不改签名

上下文里 `orderflow/pricing.py` 的函数签名是明确的，因此实现直接复用既有能力：

- `coupon_share_cents(order, sku, quantity)` —— **按 SKU 逐个调用再累加**（不是把整个
  `{sku: 数量}` 字典传进去）；
- `refund_cap_cents(order)` —— 单次退款上限；
- `order_subtotal_cents(order)` / `order_total_cents(order)` —— 金额基础计算。

### 3.3 最终代码

```python
from .models import REFUND_REASONS, REASON_DELIVERY_DELAY, Order, RefundQuote, RefundRequest
from .pricing import coupon_share_cents, refund_cap_cents


def refundable_amount(order: Order, request: RefundRequest) -> RefundQuote:
    if request.reason not in REFUND_REASONS:
        raise ValueError(f"invalid refund reason: {request.reason}")

    known_skus = {item.sku for item in order.items}
    unknown_skus = sorted(sku for sku in request.quantities if sku not in known_skus)
    if unknown_skus:
        raise ValueError(f"sku not in order {order.order_id}: {', '.join(unknown_skus)}")

    gross_goods_cents = 0
    coupon_share = 0
    for item in order.items:
        quantity = request.quantities.get(item.sku)
        if not quantity:
            continue
        gross_goods_cents += item.unit_price_cents * quantity
        coupon_share += coupon_share_cents(order, item.sku, quantity)
    goods_refund_cents = gross_goods_cents - coupon_share

    if request.reason == REASON_DELIVERY_DELAY:
        shipping_refund_cents = order.shipping_fee_cents
    else:
        shipping_refund_cents = 0

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

（完整文件含 docstring 见 `workspace/orderflow/refund.py`，逐行差异见 `docs/06-代码差异.md`。）

### 3.4 按测试反馈修正过一次

首版实现把 `goods_refund_cents` 取成了**毛额**（39900），而 `SPEC-REFUND-014` 与目标测试
要求的是**扣除优惠券分摊后的可退商品金额**（39900 − 3342 = 36558）。
运行目标测试得到 `AssertionError: assert 39900 == 36558`，据此修正为
`goods_refund_cents = gross_goods_cents - coupon_share`，随后 8/8 通过。

这条修正正是「先用上下文定规则、再用测试验证」的意义：规格与测试共同把语义钉死。

---

## 四、修改结果

| 项目 | 结果 |
| --- | --- |
| 目标功能测试 `tests/test_refund_quota.py` | 修改前 8 个全部失败（`NotImplementedError`），修改后 **8/8 通过** |
| 回归测试 `tests/test_pricing.py` + `tests/test_service.py` | 修改前后均 **8/8 通过** |
| 全量测试 | **16 passed** |
| 修改的文件 | 仅 `workspace/orderflow/refund.py`（测试文件与其它模块未改动） |

日志：`artifacts/test-before.log`、`artifacts/test-after.log`、`artifacts/test-summary.json`；
汇总表见 `docs/04-测试日志.md`。

---

## 五、模块内置的 MiniMax API 接入路径（可复现）

`sddctx agent apply` 实现了「上下文包 → MiniMax → 写回目标文件 → 跑测试 → 反馈重试」的闭环：

```bash
export MINIMAX_API_KEY=<你的 MiniMax API Key>
python -m sddctx.cli agent apply --task "…" --target orderflow/refund.py \
  --reference tests/test_refund_quota.py --reference orderflow/pricing.py --reference orderflow/models.py \
  --test-command "python -m pytest -q tests/test_refund_quota.py" \
  --record artifacts/minimax-run.json
```

本机上该路径被实际跑过多轮，记录在 `artifacts/minimax-run.json` 与
`artifacts/minimax-api-attempts.md`。过程中得到两条工程结论，都已固化进代码：

1. **必须限制写入范围**：模型第一轮曾试图连带改写 `pricing.py` / `models.py` / 测试文件，
   会破坏「测试集前后一致」的要求。现在模型输出只有 `--target` 白名单内的文件会被写入，
   其余一律拒绝并记录（`sddctx/agent.py: write_files(allowed=...)`）。
2. **必须给模型静态反馈**：模型经常「调用了但没导入」或「按直觉调用、签名不对」。
   现在每次写入后会自动做两件事——用 AST 找出**未定义的名字**、比对**既有函数的真实签名**，
   并把结论作为下一轮提示词的一部分回灌（`sddctx/agent.py: undefined_names / signature_mismatches`）。

> 结论（写入 `docs/01-运行说明.md` 的已知限制）：本机 MiniMax 开放平台账号当前可用的文本模型为
> `MiniMax-Text-01`，其代码能力不足以稳定收敛到既有函数的正确签名；因此**提交的最终实现由
> MiniMax Code（MiniMax-M3.1-Flash）在本次会话中依据上下文包完成**，
> 模块内置的 API 接入路径保持可用并留有完整调用记录，供持有更强模型凭据的评审直接重放。

---

## 六、提交内容与本次修改的对应关系

| 提交内容 | 与本次修改的关系 |
| --- | --- |
| `workspace/orderflow/refund.py` | **本次 MiniMax 修改的文件**（唯一被改动的业务代码） |
| `workspace/orderflow/pricing.py`、`models.py`、`service.py` | 未改动（被上下文引用、被回归测试覆盖） |
| `workspace/tests/*.py` | 未改动（修改前后完全一致） |
| `sddctx/*` | 上下文模块本身（本次为完成题目新写） |
| `snapshots/before/orderflow/refund.py` | 修改前的代码快照，用于复现「修改前失败」 |

## 三、上下文包（模块提供给 MiniMax 的内容）

上下文由 `sddctx context` 生成：规格与代码来源全部来自 **seekdb 的真实查询**（见 `artifacts/context-queries.log`），任务状态来自 **PowerContext**。

```markdown
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
assert quote.goods_refund_cents == 5000; assert quote.shipping_refund_cents == 0; assert quote.coupon_share_cents == 0; assert quote.cap_cents
```

> 完整上下文包见 `artifacts/context-pack.md`。

## 四、模块内置 API 接入路径的调用留档

- 模型：`MiniMax-Text-01`
- 任务：为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：按退款原因决定运费是否可退，优惠券按 SPEC-PRICE-003 分摊，并按 SPEC-REFUND-020 把单次退款金额限制为订单实付金额的 50%。需要实现的符号是 orderflow.refund.refundable_amount。
- 实际写入文件：orderflow/refund.py
- 调用与响应留档：`artifacts/minimax-run.json`

| 轮次 | 提示词长度 | 模型输出解析出的文件 | 拒绝写入的非目标文件 | 测试退出码 |
| --- | --- | --- | --- | --- |
| 1 | 22549 字符 | orderflow/refund.py | （无） | 1 |
| 2 | 22937 字符 | orderflow/refund.py | （无） | 1 |
| 3 | 22937 字符 | orderflow/refund.py | （无） | 1 |
| 4 | 22937 字符 | orderflow/refund.py | （无） | 1 |
| 5 | 22937 字符 | orderflow/refund.py | （无） | 1 |

# MiniMax API 接入路径的实际尝试记录

本文件记录 `sddctx agent apply`（上下文包 → MiniMax API → 写回目标文件 → 跑测试 → 反馈重试）
这条**可复现的程序化接入路径**在本机上的实际运行过程与结论。

凭据来自本机 `mmx` CLI 已配置的 MiniMax 开放平台账号（`~/.mmx/config.json`），
**未写入仓库**。模型为账号当前可用的 `MiniMax-Text-01`（`MiniMax-M2` / `M2.1` 在该账号返回
"The model is no longer available"）。

原始记录：

- `minimax-run.json`：最近一轮完整调用记录（请求摘要、模型原始响应、解析出的文件、测试退出码）
- `minimax-run-01-overreach.json`：第一轮（尚无写入白名单）的完整调用记录

---

## 轮次 1：模型越界修改了非目标文件

| 项 | 结果 |
| --- | --- |
| 模型输出 | 同时给出 `orderflow/refund.py`、`orderflow/pricing.py`、`orderflow/models.py`，第二轮还给出了 `tests/test_refund_quota.py` |
| 后果 | 改写了既有函数 `coupon_share_cents` 的签名（`(order, sku, quantity)` → `(order, quantities)`），并修改了测试文件 |
| 处置 | **人工还原** `pricing.py` / `models.py` / 测试文件到原始版本 |

**结论与固化**：模型必须被限制在白名单内写文件。现在 `write_files(..., allowed=...)` 会拒绝
白名单外的路径，CLI 同时把被拒绝的文件名打印到 stderr 并记入调用记录。

## 轮次 2：调用了但没导入

| 项 | 结果 |
| --- | --- |
| 模型输出 | `if request.reason not in REFUND_REASONS:` —— 但文件头没有 `from .models import REFUND_REASONS` |
| 报错 | `NameError: name 'REFUND_REASONS' is not defined`（8 个用例全部失败） |
| 处置 | 新增 AST 静态检查 `undefined_names()`，把「使用了但既没定义也没导入」的名字指出来 |

**结论与固化**：给模型的反馈不能只有测试日志，还要有精确的静态反馈。
现在每一轮写入后都会做未定义名检查，并把结论写进下一轮提示词。

## 轮次 3–5：签名用错，反馈明确但模型不收敛

| 项 | 结果 |
| --- | --- |
| 模型输出 | `coupon_share_cents(order, request.quantities)` —— 把整个 `{sku: 数量}` 字典传给了按 SKU 分摊的函数 |
| 报错 | `TypeError: coupon_share_cents() missing 1 required positional argument: 'quantity'` |
| 处置 | 新增 `signature_mismatches()`：比对模型对既有函数的调用参数个数与关键字参数，与工程里的真实签名逐个核对，并把结论回灌 |

反馈内容形如：

```
静态检查发现 `orderflow/refund.py` 里对既有函数的调用与真实签名不符：
- `coupon_share_cents` 定义在 `orderflow.pricing`，真实签名是 (order, sku, quantity)，当前调用只给了 2 个参数
```

模型在该账号可用的 `MiniMax-Text-01` 上反复回到同一个错误写法，未能收敛。

---

## 结论

1. **接入路径本身是通的**：上下文包正确组装、请求真实发往 MiniMax、响应被解析、
   文件按白名单写回、测试退出码与失败原因被回灌——整条链路可复现、可留档。
2. **模型能力是瓶颈**：当前账号可用的 `MiniMax-Text-01` 在这个任务上无法稳定收敛到
   既有函数的正确签名。因此**提交的最终实现由 MiniMax Code（MiniMax-M3.1-Flash）在本次会话中
   依据同一份上下文包完成**，详见 [`minimax-coding-session.md`](minimax-coding-session.md)。
3. **评审可直接重放**：持有更强 MiniMax 模型凭据时，执行

   ```bash
   export MINIMAX_API_KEY=<你的 MiniMax API Key>
   python -m sddctx.cli agent apply --task "…" --target orderflow/refund.py \
     --reference tests/test_refund_quota.py --reference orderflow/pricing.py --reference orderflow/models.py \
     --test-command "python -m pytest -q tests/test_refund_quota.py" \
     --record artifacts/minimax-run.json
   ```

   即可用同一条流水线重新生成 `orderflow/refund.py` 并跑通目标测试。
   可用 `MINIMAX_MODEL` / `MINIMAX_BASE_URL` / `MINIMAX_PROTOCOL` 切换模型与协议
   （`minimax` = `chatcompletion_v2`，`anthropic` = Anthropic 兼容的 `/messages`）。

## 五、修改结果与提交代码的对应关系

- 修改前：`workspace/orderflow/refund.py` 是抛 `NotImplementedError` 的桩（快照见 `snapshots/before/orderflow/refund.py`）；
- 修改后：`workspace/orderflow/refund.py` 实现 `SPEC-REFUND-014`；
- 逐行差异见 [`06-代码差异.md`](06-代码差异.md)（基准 `snapshots/before/`，对照本次提交中的 `workspace/orderflow/refund.py`）；
- 测试结果见 [`04-测试日志.md`](04-测试日志.md)。
