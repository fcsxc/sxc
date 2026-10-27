# SDD Engineering Context Module

面向持续演进工程的小型 Spec-Driven Development 上下文模块。它从 **seekdb** 中检索当前规格、相关代码和测试，从 **PowerContext** 读取任务状态，再把经过筛选的上下文交给 **MiniMax-M3** 完成一次真实代码修改。

## 演示任务

业务工程是一个工单筛选器 `filterTickets(tickets, filters)`。

任务：增加 `filters.text` 关键词过滤：

- 对标题和描述做不区分大小写的子串匹配；
- 查询字符串先去除首尾空白，空白查询不生效；
- 保持原有 `status` 与 `minPriority` 行为；
- 不修改输入数组。

规格从 v1 更新到 v2 后重新索引，上下文输出立即包含新的 `filters.text` 要求。

## 目录

```text
minimax/
├── business/ticket-service.js       # 业务代码（最终版本由 MiniMax 生成）
├── tests/ticket-service.test.js     # 目标测试与回归测试
├── specs/ticket-filter.md           # 当前规格 v2
├── specs/history/ticket-filter-v1.md
├── specs/ticket-filter-v2.md
├── scripts/                         # 上下文、PowerContext、MiniMax 辅助脚本
├── records/                         # MiniMax 请求、响应与开发记录
├── evidence/                        # 前测/后测、代码快照、diff、数据库和状态记录
├── lib/                             # seekdb 与 PowerContext 客户端
├── context-manifest.json            # 需要索引的工程资料白名单
└── package.json
```

## 技术分工

| 技术 | 实际作用 |
|---|---|
| MiniMax-M3 | 根据 seekdb 提供的规格、代码和测试，生成 `business/ticket-service.js` 的完整新版本 |
| seekdb 1.4.0 | 本地嵌入式数据库；保存工程资料，查询结果用于构造任务上下文 |
| PowerContext 1.4.1 | 保存任务完成项、待办和验证结果；新 Node 进程启动后重新读取 |

上下文模块入口：

```bash
node scripts/query-context.mjs "<开发任务>"
```

输出包含：

- `specs`：适用规格及版本
- `code`：需要修改的文件、符号和源码
- `tests`：功能与回归测试
- `taskState`：PowerContext 召回的已完成事项、待办和验证结果
- `database`：seekdb 查询信息

## 环境要求

- Node.js 22+（实际验证使用 Node.js 24）
- npm
- PowerContext 1.4.1，Python 3.11+
- MiniMax CLI 1.0.28 / MiniMax-M3 API 权限；只复现上下文和测试时不需要 MiniMax Key

## 初始化

```bash
cd minimax
npm install
```

启动 PowerContext：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install "powercontext[cli,server]==1.4.1"
powercontext config init --template --output .env
powercontext server run --env-file .env
```

另开终端创建任务 Scope：

```bash
node scripts/create-scope.mjs
export POWERCONTEXT_URL=http://127.0.0.1:8000
export POWERCONTEXT_SCOPE=<输出的 scope_id>
```

索引工程资料到 seekdb：

```bash
npm run context:index
```

默认数据库目录为 `./seekdb-data`，可通过 `SEEKDB_PATH` 修改。首次打开可能需要数秒初始化。

查询任务上下文：

```bash
npm run context:query -- "为 filterTickets 增加 text 关键词过滤，需保持 status 与 minPriority 行为不变"
```

保存并跨进程读取任务状态：

```bash
node scripts/save-task-state.mjs --scope "$POWERCONTEXT_SCOPE" \
  --task "Add text filtering to filterTickets" \
  --status "in_progress" \
  --completed "seekdb context indexed" \
  --pending "Use MiniMax to edit ticket-service.js" \
  --verification "Before-change target tests fail"

# 新进程读取
node scripts/load-task-state.mjs --scope "$POWERCONTEXT_SCOPE" \
  --query "SDD_TASK_STATE filterTickets text filtering"
```

## 验证样例

### 1. 规格更新后上下文变化

```bash
node scripts/use-spec-version.mjs v1
npm run context:index
npm run context:query -- "为 filterTickets 增加 text 关键词过滤"
```

此时 `specs[0].content` 中**没有** `filters.text` 规则。

```bash
node scripts/use-spec-version.mjs v2
npm run context:index
npm run context:query -- "为 filterTickets 增加 text 关键词过滤"
```

此时输出切换到 v2 规格，包含 `filters.text`。实际前后输出分别保存在 `evidence/context-before-spec-update.json` 和 `evidence/context-after-spec-update.json`。

### 2. 修改前后测试

修改前：

```bash
cp evidence/ticket-service.before.js business/ticket-service.js
node --test tests/ticket-service.test.js
```

实际结果：3 个回归测试通过，2 个目标测试失败；退出码 1。日志见 `evidence/tests-before.txt`。

MiniMax 修改后：

```bash
node scripts/build-minimax-request.mjs evidence/context-final.json
mmx text chat --messages-file records/minimax-request.json \
  --model MiniMax-M3 --max-tokens 4096 --temperature 0.2 \
  --non-interactive --quiet --output text > records/minimax-response.md
node scripts/apply-minimax-response.mjs records/minimax-response.md business/ticket-service.js
node --test tests/ticket-service.test.js
```

实际结果：5/5 通过，退出码 0。日志见 `evidence/tests-after.txt`，代码差异见 `evidence/code.diff`。

### 3. 状态复用

`evidence/powercontext-save-state.json` 记录写入，`evidence/powercontext-load-after-restart.json` 由另一个 Node 进程读取到 `completed` 和 `All 5 tests pass`，证明任务状态不依赖进程内存。

## 重新开始

- 删除 `seekdb-data/` 后执行 `npm run context:index`。
- 重新执行 `node scripts/create-scope.mjs` 获得新的 Scope。
- 将 `evidence/ticket-service.before.js` 复制回业务代码可重现修改前状态。

## 已知限制

- 当前检索采用关键词驱动的工程文档筛选，不是通用语义代码搜索。
- 评测覆盖的是单一小模块；跨模块依赖图未实现。
- PowerContext 和 MiniMax 需要外部服务/凭据，示例中不包含任何真实 Key。
- `@oceanbase/seekdb-node` 首次启动会在本地创建 seekdb 数据目录，需保证目录可写。
