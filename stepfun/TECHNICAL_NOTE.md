# 技术说明：LocalLens

## 1. 总体结构

LocalLens 将计算与存储明确分层：

```text
浏览器：Transformers.js → WebGPU/FP16 或 WASM/INT8 → 文本/查询向量
   │
   └─ HTTP JSON
        └─ Node 本地服务
             ├─ @oceanbase/seekdb-node 启动 seekdb
             └─ seekdb-js 1.4.0：HNSW 向量索引 + IK 全文索引 + hybridSearch
```

服务端不加载 embedding 模型，也不调用云端推理 API。浏览器提交的是已计算好的向量、原文和 metadata。

## 2. 模型与量化

- `Xenova/bge-small-zh-v1.5`，上游 `BAAI/bge-small-zh-v1.5`
- revision：`75c43b069aac4d136ba6bc1122f995fedcfd2781`
- 512 维中文/英文句向量
- WebGPU：`device: "webgpu", dtype: "fp16"`
- WASM：`device: "wasm", dtype: "q8"`

WebGPU 初始化成功时优先使用 FP16；不可用或加载失败时自动切换 WASM INT8。界面明确显示实际后端，并提示是否发生降级。

ONNX 体积：

- FP32：94,851,877 B（90.45 MiB）
- FP16：47,497,427 B（45.30 MiB）
- INT8：24,010,842 B（22.90 MiB）
- INT8 压缩比：3.95×，减少 74.34%

在 12 篇文档、4 条查询上的同一套质量测试中，三种精度的 Recall@3 均为 `0.875`，nDCG@3 均为 `0.903`。INT8 在 CPU 热路径测试中达到 491.34 docs/s。

## 3. seekdb 数据层

每个知识库使用独立 collection：`local_rag_<kb-id>`。

Schema：

- HNSW 向量索引：512 维、cosine、`embeddingFunction: null`
- IK 全文索引：`ik_mode: smart`
- metadata 保存 `doc_id`、`source`、`chunk_index`、`imported_at`

写入采用 `collection.upsert()` 支持增量导入；随后调用 `collection.refresh_index()`。检索使用：

```ts
collection.hybridSearch({
  query: { whereDocument: { $contains: query } },
  knn: { queryEmbeddings: [queryEmbedding] },
  nResults: 5,
});
```

混合召回与 RRF 融合在 seekdb 内部完成，客户端不会分别获取两路结果后自行拼接。

## 4. 状态与优化

- 知识库 ID 保存在 localStorage；切换知识库时切换到独立 collection。
- 文档按每行一个文档导入，长文本按 320 字符分成重叠文本块。
- 默认批大小 8，可切换到 4 或 16。
- 模型实例在页面生命周期内复用；查询和后续导入不再重复加载模型。
- UI 分阶段显示模型加载、文档向量化、写入与刷新、查询向量化、seekdb 检索和端到端延迟。
- 模型文件、ONNX Runtime WASM 与 WebGPU JSEP 运行文件均随应用本地提供，不依赖 CDN。

## 5. 验证

- `npm test`：4/4 通过，包括真实 seekdb 写入、刷新和混合检索。
- `npm run build`：生产构建成功。
- 浏览器 Edge Headless WASM 实测：选择 `WASM · INT8`；模型加载 851.0 ms；12 个文本块写入 33.7 ms、索引刷新 605.5 ms；混合检索返回 5 条，查询向量化 8.1 ms、seekdb 检索 12.9 ms、端到端 23.7 ms；无外部网络请求失败。
- seekdb 服务端 API 实测：写入 2 篇文档，刷新后 `hybridSearch()` 返回 2 条结果，全文命中项排名第一。
