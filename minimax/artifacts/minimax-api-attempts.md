# MiniMax API 接入路径：迭代过程与工程结论

本文件记录 `sddctx agent apply`（上下文包 → MiniMax API → 写回目标文件 → 跑测试 → 反馈重试）
这条**可复现的程序化接入路径**在本机上的迭代过程，以及从中固化下来的工程结论。

凭据来自本机 `mmx` CLI 已配置的 MiniMax 开放平台账号（`~/.mmx/config.json`），
**未写入仓库**。最终提交的实现由 **`MiniMax-M3`** 生成（官方 HTTP API
`POST https://api.minimaxi.com/v1/text/chatcompletion_v2`），调用留档见 `minimax-run.json`。

原始记录：

- `minimax-run.json`：**最终成功的一轮**（MiniMax-M3，提示词 21 334 字符，测试退出码 0）
- `minimax-run-01-overreach.json`：第一轮（尚无写入白名单）的完整调用记录

---

## 阶段一：`MiniMax-Text-01` —— 模型能力不足（未收敛）

本机账号可用的最小文本模型是 `MiniMax-Text-01`（`MiniMax-M2` / `M2.1` 在该账号返回
"The model is no longer available"）。用它跑了 5 轮：

| 轮次 | 现象 | 固化的改进 |
| --- | --- | --- |
| 1 | 模型输出同时包含 `orderflow/pricing.py`、`orderflow/models.py`，第 2 轮还包含 `tests/test_refund_quota.py`——**试图改写测试与既有函数签名** | **写入白名单**：`write_files(..., allowed=...)` 只允许 `--target` 内的文件落地，越界文件名打印到 stderr 并记入调用记录 |
| 2 | `if request.reason not in REFUND_REASONS:` 但文件头没有对应 import → `NameError` | **未定义名静态检查**：`undefined_names()` 用 AST 找出「用了但没定义也没导入」的名字，回灌给模型 |
| 3–5 | `coupon_share_cents(order, request.quantities)` —— 把整个 `{sku: 数量}` 字典传给了按 SKU 分摊的函数 → `TypeError` | **签名比对**：`signature_mismatches()` 拿工程里的真实签名逐个核对调用，回灌「真实签名是 (order, sku, quantity)，当前调用只给了 2 个参数」 |

反馈内容形如：

```
静态检查发现 `orderflow/refund.py` 里对既有函数的调用与真实签名不符：
- `coupon_share_cents` 定义在 `orderflow.pricing`，真实签名是 (order, sku, quantity)，当前调用只给了 2 个参数
请按真实签名调用。
```

**结论**：接入链路本身是通的（提示词组装 → 真实请求 → 响应解析 → 白名单写回 → 测试退出码 → 反馈回灌），
但 `MiniMax-Text-01` 的代码能力不足以稳定收敛到既有函数的正确签名。

## 阶段二：验证命令本身没跑起来（假失败）

换成 `MiniMax-M3` 重跑时，测试始终报「退出码 1」。定位后发现**根因不在模型**：

```
D:\work of minimax\.venv-minimax\Scripts\python.exe -m pytest ...
```

验证命令以 `shell=True` 执行，而该可执行文件路径**含空格且未加引号**，
shell 实际报的是「`'D:\work' 不是内部或外部命令`」——**pytest 根本没被启动**，
模型拿到的是 shell 报错而不是测试反馈，于是每一轮都在原地打转。

**固化**：CLI 新增 `--test-argv`（列表形式，直接 `subprocess.run(list)`，不经 shell），
可执行文件路径含空格也不会被拆开；`--test-command` 仍保留给复合命令，并在帮助里注明引号要求。

## 阶段三：`MiniMax-M3` —— 一次通过

改用 `--test-argv` 后重跑：

```
[MiniMax] 第 1 次请求，提示词 21334 字符 …
[MiniMax] 已写入：orderflow/refund.py
[test] 退出码 0
```

- 模型：`MiniMax-M3`
- 接口：`POST https://api.minimaxi.com/v1/text/chatcompletion_v2`
- 输入：任务 + seekdb 检索出的上下文包 + 目标文件（修改前的桩）+ 只读参考文件 + 硬性约束
- 输出：`### FILE: orderflow/refund.py` + 完整代码块
- 写入：仅白名单内的目标文件
- 验证：目标测试退出码 0

同一份流水线也支持官方 `mmx` 命令行：

```bash
python -m sddctx.cli agent apply --task "…" --target orderflow/refund.py \
  --protocol mmx-cli --model MiniMax-M3 \
  --test-argv <python> -m pytest -q tests/test_refund_quota.py
```

（`mmx` 为 npm 全局垫片 `.cmd`，模块在 Windows 上会自动用 shell 调用并解析真实路径。）

---

## 评审如何重放

```bash
export MINIMAX_API_KEY=<你的 MiniMax API Key>     # 或先执行 mmx auth login
python -m sddctx.cli agent apply --task "…" --target orderflow/refund.py \
  --reference tests/test_refund_quota.py --reference orderflow/pricing.py --reference orderflow/models.py \
  --protocol minimax --model MiniMax-M3 \
  --test-argv <python> -m pytest -q tests/test_refund_quota.py \
  --record artifacts/minimax-run.json
```

会得到同样的「上下文包 → MiniMax → 写回目标文件 → 目标测试通过」流水线，
并留下同样格式的调用留档。
