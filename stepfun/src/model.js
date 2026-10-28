import { env, pipeline } from "@huggingface/transformers";
import wasmFactoryUrl from "onnxruntime-web/ort-wasm-simd-threaded.asyncify.mjs?url";
import wasmBinaryUrl from "onnxruntime-web/ort-wasm-simd-threaded.asyncify.wasm?url";
import webgpuKernelUrl from "onnxruntime-web/ort-wasm-simd-threaded.jsep.mjs?url";
import webgpuBinaryUrl from "onnxruntime-web/ort-wasm-simd-threaded.jsep.wasm?url";
import {
  FALLBACK_BATCH_SIZE,
  MODEL_ID,
  MODEL_REVISION,
  VECTOR_DIMENSION,
} from "../shared/constants.mjs";

env.allowLocalModels = true;
env.allowRemoteModels = false;
env.localModelPath = '/models/';
env.remoteHost = "https://hf-mirror.com";
env.remotePathTemplate = "{model}/resolve/{revision}/";
function configureOnnxRuntime(device) {
  const wasm = env.backends?.onnx?.wasm;
  if (!wasm) return;
  wasm.numThreads = 1;
  wasm.proxy = false;
  wasm.wasmPaths = device === "webgpu"
    ? { mjs: webgpuKernelUrl, wasm: webgpuBinaryUrl }
    : { mjs: wasmFactoryUrl, wasm: wasmBinaryUrl };
}

async function canUseWebGPU() {
  if (!navigator.gpu) return false;
  try {
    return Boolean(await navigator.gpu.requestAdapter());
  } catch {
    return false;
  }
}

function backendPlan(hasWebGPU) {
  if (hasWebGPU) {
    return [
      { device: "webgpu", dtype: "fp16", label: "WebGPU · FP16" },
      { device: "wasm", dtype: "q8", label: "WASM · INT8" },
    ];
  }
  return [{ device: "wasm", dtype: "q8", label: "WASM · INT8" }];
}

export async function loadLocalEmbedder({ onProgress = () => {}, onBackend = () => {} } = {}) {
  const start = performance.now();
  const hasWebGPU = await canUseWebGPU();
  const plan = backendPlan(hasWebGPU);
  let lastError;

  for (const attempt of plan) {
    configureOnnxRuntime(attempt.device);
    onBackend({ status: "loading", ...attempt, webgpuAvailable: hasWebGPU });
    try {
      const extractor = await pipeline("feature-extraction", MODEL_ID, {
        revision: MODEL_REVISION,
        device: attempt.device,
        dtype: attempt.dtype,
        progress_callback: onProgress,
      });
      const loadMs = performance.now() - start;
      onBackend({ status: "ready", ...attempt, webgpuAvailable: hasWebGPU, loadMs });
      return {
        extractor,
        ...attempt,
        webgpuAvailable: hasWebGPU,
        loadMs,
        modelId: MODEL_ID,
        revision: MODEL_REVISION,
        dimension: VECTOR_DIMENSION,
      };
    } catch (error) {
      lastError = error;
      onBackend({
        status: "fallback",
        ...attempt,
        webgpuAvailable: hasWebGPU,
        error: error.message,
      });
    }
  }

  throw new Error(`模型加载失败：${lastError?.message ?? "unknown error"}`);
}

export async function embedTexts(embedder, texts, options = {}) {
  const batchSize = options.batchSize ?? FALLBACK_BATCH_SIZE;
  const onProgress = options.onProgress ?? (() => {});
  const vectors = [];
  const started = performance.now();

  for (let offset = 0; offset < texts.length; offset += batchSize) {
    const batch = texts.slice(offset, offset + batchSize);
    const output = await embedder.extractor(batch, {
      pooling: "mean",
      normalize: true,
    });
    const rows = output.tolist();
    vectors.push(...rows);
    onProgress(Math.min(offset + batch.length, texts.length), texts.length);
  }

  const elapsedMs = performance.now() - started;
  return {
    vectors,
    elapsedMs,
    throughput: texts.length / Math.max(elapsedMs / 1000, 0.001),
  };
}
