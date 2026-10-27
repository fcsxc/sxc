# 技术说明：规有所依

## 模块结构

```text
开发任务
  -> query-context.mjs
      -> seekdb: 查询已索引的 spec / code / test
      -> PowerContext: 召回任务完成项、待办和验证结果
  -> 组装最小开发上下文
  -> MiniMax-M3: 生成业务代码修改
  -> node:test: 目标测试 + 回归测试
  -> save-task-state.mjs: 将验证结果写回 PowerContext
```

## 上下文选择

`context-manifest.json` 是工程资料白名单。`index-context.mjs` 读取规格、源码和测试，将真实路径、符号、版本和正文写入 seekdb 的 `engineering_docs` 表。

`query-context.mjs` 从该表查询文档，并对中英文关键词与中文双字片段进行相关性打分。输出只引用 seekdb 中实际存在的来源。规格文件与 manifest 更新后执行重新索引，后续查询会返回新内容，而不是固定答案。

## 技术分工

### seekdb

实际使用 `@oceanbase/seekdb-node` 1.4.0 启动嵌入式 seekdb，并通过 `mysql2` 执行建表、写入、查询。运行记录包含 3 条工程文档以及查询后得到的规范、代码和测试正文。

### PowerContext

使用 1.4.1 HTTP API：

- `POST /v1/scopes` 创建任务边界；
- `POST /v1/memory/remember` 保存阶段状态和最终验证结果；
- `POST /v1/context/prepare` 在后续进程中召回状态。

### MiniMax

使用 `mmx-cli` 调用 `MiniMax-M3`。输入只包含 seekdb/PowerContext 形成的开发上下文、任务约束和测试。模型返回完整替换文件，`apply-minimax-response.mjs` 抽取代码块后覆盖 `business/ticket-service.js`。请求、响应和哈希保存在 `records/`。

## 验证

- 修改前：3 个回归测试通过，2 个目标测试失败，退出码 1。
- 修改后：5/5 测试通过，退出码 0。
- 规格 v1 重导入后上下文不含 `filters.text`；规格 v2 重导入后包含该规则。
- 新进程可读取 PowerContext 中 `completed` 和 `All 5 tests pass` 状态。

## 边界

模块面向轻量工程上下文演示，不构建完整调用图，也不替代完整 SDD 平台。关键词选择是可解释、低延迟的实现，后续可替换为 seekdb 的向量/混合检索。
