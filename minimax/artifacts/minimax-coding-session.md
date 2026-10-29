# MiniMax 开发记录（本次任务）

> 本文件记录 **MiniMax 在本次任务中的实际参与**：任务是什么、上下文模块提供了什么、
> MiniMax 通过什么接口生成了哪份代码、结果如何。与提交的代码差异逐行对应。

---

## 一、收到的任务

来自赛题《规有所依——面向软件持续演进的 SDD 上下文管理系统》（MiniMax × OceanBase 赛道，20 分）：

> 为已有 AI 开发助手实现或改进工程上下文模块，根据开发任务提供当前有效的规格、相关代码和测试，
> 并通过实际代码修改验证效果。

技术要求：使用 **MiniMax** 参与代码修改；使用 **seekdb 或 OceanBase** 存储、检索工程资料；
使用 **PowerContext** 保存并复用任务状态。

本作品定义的开发任务：

> 为 OrderFlow 的 `orderflow.refund` 模块实现 `SPEC-REFUND-014`：按退款原因决定运费是否可退，
> 优惠券按 `SPEC-PRICE-003` 分摊，并按 `SPEC-REFUND-020` 把单次退款金额限制为订单实付金额的 50%。
> 需要实现的符号是 `orderflow.refund.refundable_amount`。

---

## 二、上下文模块先给出上下文（MiniMax 才开始动手）

写代码之前，先让上下文模块产出上下文包——**没有这一步，MiniMax 就是在盲写**。

```bash
$ python -m sddctx.cli import
规格条目 9 条，代码符号 32 个，测试用例 16 个
seekdb 统计：{'spec_item': 9, 'code_symbol': 32, 'test_case': 16}

$ python -m sddctx.cli context --task "为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：…" \
      --out artifacts/context-pack.md
```

上下文包给出四类信息（完整内容见 `artifacts/context-pack.md`）：

1. **适用的规格条目**：`SPEC-REFUND-014`、`SPEC-REFUND-020`、`SPEC-PRICE-003`、`SPEC-REFUND-001`，
   含正文与来源文件路径；
2. **已失效的决策**：`SPEC-REFUND-012`「运费一律不退」已被 `SPEC-REFUND-014` 取代，
   上下文明确标注**不得**作为约束——避免了把旧规则写进实现；
3. **需要修改的代码**：`orderflow/refund.py::refundable_amount`（修改前是抛
   `NotImplementedError` 的桩），以及只读参考 `orderflow/pricing.py` 的
   `order_subtotal_cents` / `order_total_cents` / `coupon_share_cents` / `refund_cap_cents`
   与 `orderflow/models.py` 的 `Order` / `RefundRequest` / `RefundQuote` / `REFUND_REASONS`；
4. **测试**：目标功能测试 `tests/test_refund_quota.py` 的 8 个用例（含断言要点），
   回归测试 `tests/test_pricing.py` / `tests/test_service.py`。

以上规格、代码、测试全部来自 **seekdb 的真实 SQL 查询**（`artifacts/context-queries.log` 共 12 条，
含 `MATCH(search_text) AGAINST(...)` 全文检索），任务状态来自 **PowerContext**。

> 关键点：送进模型之前，seekdb 里索引的是**修改前**的代码（`NotImplementedError` 桩）。
> 上下文里没有答案，模型必须自己依据规格与测试把实现写出来。

---

## 三、MiniMax 的调用与产出

```bash
$ python -m sddctx.cli agent apply \
    --task "为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：…" \
    --target orderflow/refund.py \
    --reference tests/test_refund_quota.py \
    --reference orderflow/pricing.py \
    --reference orderflow/models.py \
    --protocol minimax --model MiniMax-M3 \
    --test-argv <python> -m pytest -q tests/test_refund_quota.py \
    --record artifacts/minimax-run.json
```

调用留档（`artifacts/minimax-run.json`）：

| 项 | 值 |
| --- | --- |
| 模型 | `MiniMax-M3` |
| 接口 | `POST https://api.minimaxi.com/v1/text/chatcompletion_v2`（官方 HTTP API） |
| 提示词规模 | 21 334 字符（任务 + 上下文包 + 目标文件 + 只读参考文件 + 约束） |
| 模型输出 | `### FILE: orderflow/refund.py` + 完整文件代码块 |
| 写入 | 仅 `orderflow/refund.py`（白名单内），无越界写入 |
| 验证 | 目标测试退出码 **0** |

模型原始响应（节选）：

```text
### FILE: orderflow/refund.py
```python
"""退款额度计算。

适用规格：
- ``SPEC-REFUND-014`` 退款额度计算规则
- ``SPEC-REFUND-001`` 退款原因枚举与必填校验
- ``SPEC-REFUND-020`` 单次退款金额上限
"""

from __future__ import annotations

from .models import (
    REASON_DELIVERY_DELAY,
    REFUND_REASONS,
    Order,
    RefundQuote,
    RefundRequest,
)
from .pricing import coupon_share_cents, refund_cap_cents


def refundable_amount(order: Order, request: RefundRequest) -> RefundQuote:
    """按 ``SPEC-REFUND-014`` 计算本次退款请求的可退金额。"""

    if request.reason not in REFUND_REASONS:
        raise ValueError(f"unknown refund reason: {request.reason}")
    ...
```
```

---

## 四、MiniMax 写出来的实现要点

模型从上下文里提取并实现了这些规则（与规格逐条对应）：

| 规则 | 来源规格 | 模型的做法 |
| --- | --- | --- |
| 退款原因必须属于枚举，否则 `ValueError` | `SPEC-REFUND-001` | `if request.reason not in REFUND_REASONS: raise ValueError(...)` |
| 可退商品金额 = 退款商品小计 − 分摊的优惠券抵扣 | `SPEC-REFUND-014` + `SPEC-PRICE-003` | 逐 SKU 累加 `coupon_share_cents(order, sku, quantity)`，再从毛额里扣掉 |
| 运费仅在 `delivery_delay` 时可退 | `SPEC-REFUND-014`（取代 `SPEC-REFUND-012`） | `order.shipping_fee_cents if request.reason == REASON_DELIVERY_DELAY else 0` |
| 单次退款上限 = 订单实付金额的 50%，超出截断并标记 | `SPEC-REFUND-020` | `clamped = uncapped > cap_cents`，`refundable_cents = min(uncapped, cap_cents)` |

模型**没有**修改既有函数签名，**没有**动测试文件，**没有**引入上下文之外的规则。

---

## 五、修改结果

| 项目 | 结果 |
| --- | --- |
| 目标功能测试 `tests/test_refund_quota.py` | 修改前 8 个全部失败（`NotImplementedError`）→ 修改后 **8/8 通过** |
| 回归测试 `tests/test_pricing.py` + `tests/test_service.py` | 修改前后均 **8/8 通过** |
| 全量测试 | **16 passed** |
| 修改的文件 | 仅 `workspace/orderflow/refund.py`（测试文件与其它模块未改动） |

日志：`artifacts/test-before.log`、`artifacts/test-after.log`、`artifacts/test-summary.json`；
汇总表见 `docs/04-测试日志.md`。

---

## 六、提交内容与本次修改的对应关系

| 提交内容 | 与本次修改的关系 |
| --- | --- |
| `workspace/orderflow/refund.py` | **MiniMax-M3 通过模块生成的唯一被改动文件** |
| `workspace/orderflow/pricing.py`、`models.py`、`service.py` | 未改动（被上下文引用、被回归测试覆盖） |
| `workspace/tests/*.py` | 未改动（修改前后完全一致） |
| `sddctx/*` | 上下文模块本身（本次为完成题目新写） |
| `snapshots/before/orderflow/refund.py` | 修改前的代码快照，用于复现「修改前失败」 |
| `artifacts/minimax-run.json` | MiniMax 调用与响应的原始留档 |

---

## 七、过程中固化的三条工程结论

1. **模型输出必须限制写入范围**（见 [`minimax-api-attempts.md`](minimax-api-attempts.md)）：
   早期模型曾试图连带改写 `pricing.py` / 测试文件，会破坏「测试集前后一致」的要求。
   现在只有 `--target` 白名单内的文件会被写入，其余一律拒绝并记录。
2. **要给模型精确的静态反馈**：模型常犯「调用了但没导入」「按直觉调用、签名不对」。
   现在每轮写入后自动用 AST 找出未定义名、比对既有函数真实签名，作为反馈回灌。
3. **验证命令不要交给 shell 拼字符串**：可执行文件路径含空格时会被 shell 拆开，
   导致「测试其实没跑」却只看到退出码 1。现在提供 `--test-argv`（列表形式，不经 shell），
   从根上避免这类假失败。
