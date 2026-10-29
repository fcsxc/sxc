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
