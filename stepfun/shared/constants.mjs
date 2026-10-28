export const MODEL_ID = "Xenova/bge-small-zh-v1.5";
export const MODEL_REVISION = "75c43b069aac4d136ba6bc1122f995fedcfd2781";
export const MODEL_SOURCE = `https://hf-mirror.com/${MODEL_ID}`;
export const VECTOR_DIMENSION = 512;

export const MODEL_SIZES = {
  fp32Onnx: 94_851_877,
  fp16Onnx: 47_497_427,
  int8Onnx: 24_010_842,
  tokenizerBundle: 441_007,
};

export const SAMPLE_DOCUMENTS = [
  { id: "doc-seekdb-hybrid", text: "seekdb 支持向量相似度与全文检索融合，hybridSearch 会在数据库内部完成召回和重排。", source: "seekdb-guide" },
  { id: "doc-browser-embedding", text: "Transformers.js 可以在浏览器本地运行 ONNX embedding 模型，文档和查询无需发送到云端推理服务。", source: "transformers-js" },
  { id: "doc-webgpu", text: "WebGPU 将模型计算交给本地显卡，适合在支持的 Chrome 和 Edge 浏览器中加速 embedding 推理。", source: "webgpu" },
  { id: "doc-wasm", text: "当浏览器不支持 WebGPU 时，ONNX Runtime Web 可以自动切换到 WASM 后端继续完成端侧推理。", source: "wasm" },
  { id: "doc-int8", text: "INT8 动态量化减少模型权重体积并提升 CPU 端推理速度，但需要核对量化前后的检索质量。", source: "quantization" },
  { id: "doc-refresh", text: "增量写入 seekdb 后调用 refresh_index，新导入的文档才能立刻参与向量索引检索。", source: "seekdb-refresh" },
  { id: "doc-session", text: "每个知识库使用独立 collection，并在浏览器的 localStorage 中保存当前知识库 ID，实现会话状态恢复。", source: "state" },
  { id: "doc-batching", text: "批量 embedding 可以减少模型调用次数和调度开销，批次过大则会增加首包等待时间和内存占用。", source: "performance" },
  { id: "doc-chinese-search", text: "中文全文检索使用 IK 分词器，查询数据库和本地知识库时可以匹配稳定、分词器、持久化等词项。", source: "fts" },
  { id: "doc-privacy", text: "端侧向量化适合个人知识库和隐私文档，因为原文和向量都只在本地浏览器、Node 服务和 seekdb 之间流转。", source: "privacy" },
  { id: "doc-vector", text: "Dense embedding 将语义相近的文本映射到相邻向量，余弦相似度常用于比较句向量。", source: "vector-search" },
  { id: "doc-metadata", text: "文档 ID、来源和分块序号作为 metadata 随向量写入 seekdb，检索结果可以回显对应原文。", source: "metadata" },
];

export const EVAL_QUERIES = [
  { query: "数据库内部做向量和全文混合检索", relevant: ["doc-seekdb-hybrid"] },
  { query: "浏览器没有 WebGPU 怎么办", relevant: ["doc-wasm", "doc-webgpu"] },
  { query: "怎样让新文档马上能搜到", relevant: ["doc-refresh"] },
  { query: "减少模型调用次数和内存占用", relevant: ["doc-batching"] },
];

export const FALLBACK_BATCH_SIZE = 8;
