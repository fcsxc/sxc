# LocalLens：端侧 AI 推理与 seekdb 混合检索

一个可在浏览器本地完成文档/查询向量化，并使用 seekdb 完成向量 + 全文混合检索的迷你知识库。

## 功能

1. 导入一批文本，每行作为一个文档。
2. 使用 Transformers.js 在浏览器中生成 512 维 embedding。
3. 将原文、向量、文档 ID 和 metadata 写入本地 seekdb。
4. 写入后调用 `refresh_index()`，使新文档立即可检索。
5. 在浏览器本地生成查询向量，由 seekdb `hybridSearch()` 完成向量 + IK 全文融合检索。
6. 展示排序结果、原文、来源、当前推理后端和分阶段耗时。
7. 使用独立 collection 与 localStorage 保存知识库会话，实现知识库切换和增量导入。

## 技术方案

```text
Browser
  ├─ Transformers.js / ONNX Runtime Web
  │    ├─ WebGPU + FP16（优先）
  │    └─ WASM + INT8（自动降级）
  └─ HTTP JSON API
       └─ Node local service
            ├─ @oceanbase/seekdb-node（本地 seekdb server）
            └─ seekdb-js 1.4.0
                 ├─ Dense vector index / HNSW / cosine
                 ├─ Fulltext index / IK smart mode
                 └─ collection.hybridSearch(...)
```

模型推理只发生在浏览器中。Node 服务仅接收向量、文本和元数据，不调用任何模型或云端推理 API。

## 模型与量化

- 模型：`Xenova/bge-small-zh-v1.5`
- 上游模型：`BAAI/bge-small-zh-v1.5`
- Transformers.js revision：`75c43b069aac4d136ba6bc1122f995fedcfd2781`
- 模型来源：https://hf-mirror.com/Xenova/bge-small-zh-v1.5
- 向量维度：512
- WebGPU：`dtype: "fp16"`
- WASM：`dtype: "q8"`（INT8）

| 运行文件 | 大小 |
|---|---:|
| FP32 ONNX | 94,851,877 B / 90.45 MiB |
| FP16 ONNX | 47,497,427 B / 45.30 MiB |
| INT8 ONNX | 24,010,842 B / 22.90 MiB |
| FP32 完整运行时 | 95,292,884 B / 90.88 MiB |
| INT8 完整运行时 | 24,451,849 B / 23.32 MiB |

ONNX 压缩比：**3.95×**；完整运行时压缩比：**3.90×**。详细数据见 `evidence/model-size-report.json`。

ONNX 模型、ONNX Runtime WASM 与 WebGPU JSEP 运行文件均随应用本地提供，避免评测时访问 CDN。WebGPU 不可用或初始化失败时会自动降级到本地 WASM INT8。

## seekdb 使用

本地服务通过 `@oceanbase/seekdb-node` 启动 seekdb，再通过 `seekdb` JavaScript SDK 操作数据库。

每个知识库对应独立 collection：

```text
local_rag_<knowledge-base-id>
```

Schema：

- 全文索引：`FulltextIndexConfig("ik", { ik_mode: "smart" })`
- 向量索引：HNSW，512 维，cosine
- `embeddingFunction: null`：向量全部由浏览器本地计算
- metadata：`doc_id`、`source`、`chunk_index`、`imported_at`

检索调用：

```js
collection.hybridSearch({
  query: { whereDocument: { $contains: query } },
  knn: { queryEmbeddings: [queryEmbedding] },
  nResults: 5,
});
```

因此向量和全文两路召回与融合排序都由 seekdb 执行，客户端不会分别查询两路后自行拼接。

## 启动

要求 Node.js 22+。

```bash
cd stepfun
npm ci
npm run dev
```

打开 `http://127.0.0.1:8787`。

开发模式由 Express 挂载 Vite；生产模式：

```bash
npm run build
npm start
```

数据库默认保存在 `data/seekdb-rag`，可修改 `SEEKDB_PATH`。可通过 `PORT` 修改服务端口。

## 验证样例

1. 打开页面，点击“加载端侧模型”，观察状态栏显示 `WebGPU · FP16` 或 `WASM · INT8`。
2. 点击“载入示例”，将 12 条中英文文档放入输入框。
3. 点击“向量化并写入 seekdb”，等待状态显示写入与索引刷新完成。
4. 输入：`怎样让新文档马上能搜到？`
5. 点击“混合检索”，结果中应包含“增量写入 seekdb 后调用 refresh_index……”原文。
6. 点击“新建”生成新知识库 ID，再检索时不应混入旧知识库内容。
7. 刷新页面后，知识库 ID 应从 localStorage 恢复，seekdb 中原有文档仍可检索。

## 实测结果

质量测试使用 12 篇文档、4 条查询，按同一批文本计算 Recall@3 与 nDCG@3：

| 精度 | 文档吞吐 | 查询延迟中位数 | Recall@3 | nDCG@3 |
|---|---:|---:|---:|---:|
| FP32 | 325.95 docs/s | 2.30 ms | 0.875 | 0.903 |
| INT8 | 491.34 docs/s | 1.85 ms | 0.875 | 0.903 |
| FP16 | 240.19 docs/s | 2.28 ms | 0.875 | 0.903 |

上述为 Transformers.js 在 Node/onnxruntime-node CPU 上的确定性质量与热路径测试，用于比较同一模型精度；浏览器接口会在页面“本次操作实测”区域实时记录 WebGPU/WASM 的模型加载、文档向量化、索引刷新、查询向量化、seekdb 检索和端到端耗时。

seekdb 端到端测试：

- 写入 2 篇文档并调用 `refresh_index()`；
- `hybridSearch()` 返回 2 条结果；
- 全文命中文档排名第一；
- 检索耗时约 28 ms。

原始结果见：

- `evidence/browser-wasm-result.json`
- `evidence/browser-wasm.png`
- `evidence/quality-results.json`
- `evidence/model-size-report.json`
- `evidence/seekdb-api-smoke.json`
- `evidence/tests.txt`
- `evidence/build.txt`

## 测试命令

```bash
npm test
npm run build
npm run benchmark:quality
```

`npm run benchmark:quality` 需要访问 `hf-mirror.com` 下载 FP32/FP16 ONNX 变体用于质量对比；应用运行所需的 INT8 模型已随仓库放在 `public/models/`，WASM 主流程不依赖该下载。

## 已知限制

- 图片知识库不是必做项，本版本只处理文本。
- WebGPU 依赖浏览器与显卡驱动；不支持或初始化失败时会自动使用 WASM。
- 当前混合检索权重使用 seekdb 的默认 RRF 配置。
- 首次模型加载仍包含本地 24 MB ONNX 文件读取和 ONNX Runtime WASM 初始化，后续请求复用已加载模型。
