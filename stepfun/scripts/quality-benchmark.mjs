import path from "node:path";
import { env, pipeline } from "@huggingface/transformers";
import {
  EVAL_QUERIES,
  MODEL_ID,
  MODEL_REVISION,
  MODEL_SIZES,
  SAMPLE_DOCUMENTS,
} from "../shared/constants.mjs";

env.allowLocalModels = false;
env.allowRemoteModels = true;
env.remoteHost = "https://hf-mirror.com";
env.remotePathTemplate = "{model}/resolve/{revision}/";
env.cacheDir = path.resolve(".cache/transformers");

function cosine(left, right) {
  let value = 0;
  for (let index = 0; index < left.length; index += 1) value += left[index] * right[index];
  return value;
}

function evaluate(docVectors, queryVectors) {
  let recallSum = 0;
  let ndcgSum = 0;
  const perQuery = [];
  EVAL_QUERIES.forEach((item, queryIndex) => {
    const ranked = SAMPLE_DOCUMENTS.map((document, index) => ({
      id: document.id,
      score: cosine(queryVectors[queryIndex], docVectors[index]),
    })).sort((left, right) => right.score - left.score).slice(0, 3);
    const relevance = new Set(item.relevant);
    const hits = ranked.filter((entry) => relevance.has(entry.id)).length;
    const recall = hits / Math.min(3, relevance.size);
    const dcg = ranked.reduce((sum, entry, index) => sum + (relevance.has(entry.id) ? 1 / Math.log2(index + 2) : 0), 0);
    const ideal = Array.from({ length: Math.min(3, relevance.size) }, (_, index) => 1 / Math.log2(index + 2)).reduce((a, b) => a + b, 0);
    const ndcg = ideal ? dcg / ideal : 0;
    recallSum += recall;
    ndcgSum += ndcg;
    perQuery.push({ query: item.query, rankedIds: ranked.map((entry) => entry.id), recall, ndcg });
  });
  return { recallAt3: recallSum / EVAL_QUERIES.length, ndcgAt3: ndcgSum / EVAL_QUERIES.length, perQuery };
}

async function runPrecision(dtype) {
  const loadStart = performance.now();
  const extractor = await pipeline("feature-extraction", MODEL_ID, {
    revision: MODEL_REVISION,
    device: "cpu",
    dtype,
  });
  const loadMs = performance.now() - loadStart;
  const docTexts = SAMPLE_DOCUMENTS.map((document) => document.text);
  const queryTexts = EVAL_QUERIES.map((item) => item.query);
  await extractor(docTexts.slice(0, 2), { pooling: "mean", normalize: true });

  const embedStart = performance.now();
  const docTensor = await extractor(docTexts, { pooling: "mean", normalize: true });
  const docEmbedMs = performance.now() - embedStart;
  const queryTensor = await extractor(queryTexts, { pooling: "mean", normalize: true });
  const queryVectors = queryTensor.tolist();
  const docVectors = docTensor.tolist();
  const quality = evaluate(docVectors, queryVectors);

  const latencySamples = [];
  for (let repeat = 0; repeat < 5; repeat += 1) {
    const queryStart = performance.now();
    await extractor([queryTexts[0]], { pooling: "mean", normalize: true });
    latencySamples.push(performance.now() - queryStart);
  }
  latencySamples.sort((a, b) => a - b);
  return {
    dtype,
    loadMs,
    docEmbedMs,
    docThroughput: docTexts.length / Math.max(docEmbedMs / 1000, 0.001),
    queryLatencyMedianMs: latencySamples[2],
    quality,
  };
}

const results = [];
const failures = [];
for (const dtype of ["fp32", "q8", "fp16"]) {
  try {
    results.push(await runPrecision(dtype));
  } catch (error) {
    failures.push({ dtype, error: error.message });
  }
}

console.log(JSON.stringify({
  runtime: "Transformers.js on Node/onnxruntime-node CPU",
  browserNote: "WebGPU/WASM runtime timings are recorded live by the browser UI.",
  model: MODEL_ID,
  revision: MODEL_REVISION,
  corpusDocuments: SAMPLE_DOCUMENTS.length,
  queries: EVAL_QUERIES.length,
  sizes: {
    ...MODEL_SIZES,
    onnxCompressionRatioInt8: MODEL_SIZES.fp32Onnx / MODEL_SIZES.int8Onnx,
  },
  results,
  failures,
}, null, 2));
