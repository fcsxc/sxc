# 运行证据

| 文件 | 说明 |
|---|---|
| `quality-results.json` | Transformers.js 对 FP32 / INT8 / FP16 的实际质量与热路径测试 |
| `model-size-report.json` | BGE 模型文件实际大小、运行时总量和压缩比 |
| `seekdb-api-smoke.json` | seekdb-js 写入、refresh_index 与 hybridSearch 的 API 实测结果 |
| `tests.txt` | `npm test` 输出，4/4 通过 |
| `build.txt` | Vite 生产构建输出，退出码 0 |
| `browser-wasm-result.json` | Edge Headless 端侧 WASM 模型加载、12 个文本块写入和完整混合检索结果 |
| `browser-wasm.png` | 浏览器完成导入与混合检索后的界面截图 |

关键结果：

- INT8 ONNX：22.90 MiB，对 FP32 压缩 3.95×
- Recall@3：FP32/INT8/FP16 均为 0.875
- nDCG@3：三种精度均为 0.903
- seekdb 混合检索：全文命中项排名第一
- 浏览器 WASM：模型加载 851.0 ms；12 个文本块写入 33.7 ms，索引刷新 605.5 ms；检索返回 5 条，端到端 23.7 ms，外部请求失败 0 次
