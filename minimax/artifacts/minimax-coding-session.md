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
