import { env, pipeline } from "@huggingface/transformers";
env.allowRemoteModels = true;
env.allowLocalModels = false;
env.remoteHost = "https://hf-mirror.com";
const extractor = await pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2", {
  dtype: "q8",
});
const out = await extractor(["数据库混合检索", "浏览器本地推理"], { pooling: "mean", normalize: true });
console.log(out.dims, out.data.slice(0, 5));
