# 规有所依 —— 面向软件持续演进的 SDD 上下文管理系统

> OceanBase 数据库大赛 · **MiniMax × OceanBase** 赛道作品
>
> 为 AI 开发助手实现**工程上下文模块**：根据开发任务给出**当前有效的规格、相关代码和测试**，
> 保存任务状态并可在重启后复用，最后用一次真实的代码修改验证模块确实起作用。

三项技术在流程中各自承担职责，不是"装了就算"：

| 技术 | 承担的作用 | 落点 |
| --- | --- | --- |
| **seekdb**（嵌入式 OceanBase） | 存储工程资料与索引，**真实查询结果**用于构造上下文 | `spec_item` / `code_symbol` / `test_case` + IK 分词全文索引 |
| **PowerContext** | 保存任务进展与验证结果，后续运行读回复用 | Memory 条目 + Scope，HTTP API |
| **MiniMax** | 参与本次任务的代码生成与修改 | `sddctx/agent.py` 组装上下文并调用 MiniMax API |

---

## 快速开始

```bash
cd minimax

# 1) 依赖 + 导入 + 构造上下文
bash start.sh                     # Windows: start.bat

# 2) 另开一个终端：启动 PowerContext（保存/复用任务状态）
bash scripts/start_powercontext.sh

# 3) 跑完整验证样例
bash scripts/verify_all.sh
```

详细说明见 [`docs/01-运行说明.md`](docs/01-运行说明.md)。

---

## 目录

```
minimax/
├── sddctx/         上下文模块（导入 → 检索 → 组装 → 状态存取 → 驱动 MiniMax 改代码）
├── workspace/      业务工程 OrderFlow（本次被修改的对象，含规格与测试）
├── scripts/        初始化 / 启动 / 验证脚本
├── snapshots/      修改前代码快照（复现「修改前失败」用）
├── artifacts/      运行留档：上下文包、SQL 查询记录、测试日志、MiniMax 调用记录
└── docs/           全部提交材料
```

## 提交材料索引

| 文档 | 对应题面要求 |
| --- | --- |
| [`docs/01-运行说明.md`](docs/01-运行说明.md) | 运行说明：依赖版本、配置步骤、数据初始化、调用入口、测试命令、已知限制 |
| [`docs/02-验证样例.md`](docs/02-验证样例.md) | 验证样例：任务描述、有效规格、初始数据、操作步骤、预期结果、重置方法 |
| [`docs/03-技术使用记录.md`](docs/03-技术使用记录.md) | 技术使用记录：MiniMax 开发记录、数据库查询记录、PowerContext 状态写入与复用记录 |
| [`docs/04-测试日志.md`](docs/04-测试日志.md) | 测试日志：命令、退出码、对应代码版本 |
| [`docs/05-MiniMax-开发记录.md`](docs/05-MiniMax-开发记录.md) | MiniMax 开发记录：本次任务、提供的上下文、代码修改过程 |
| [`docs/06-代码差异.md`](docs/06-代码差异.md) | 代码差异：修改前后快照与逐行 diff |
| [`docs/07-一页技术说明.md`](docs/07-一页技术说明.md) | 一页技术说明：模块结构、上下文选择方式、三项技术分工 |

---

## 演示任务

> 为 OrderFlow 的 `orderflow.refund` 模块实现 `SPEC-REFUND-014`：按退款原因决定运费是否可退，
> 优惠券按 `SPEC-PRICE-003` 分摊，并按 `SPEC-REFUND-020` 把单次退款金额限制为订单实付金额的 50%。

- 业务工程：`workspace/orderflow/`（纯标准库、可运行、带测试）
- 修改前：`orderflow/refund.py::refundable_amount` 抛 `NotImplementedError` → 目标测试失败
- 修改后：目标测试 8/8 通过，回归测试 8/8 通过
- 上下文同时给出**当前有效规格**与**已失效规格**（`SPEC-REFUND-012` 已被 `SPEC-REFUND-014` 取代）
