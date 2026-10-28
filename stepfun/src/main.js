import "./style.css";
import { api } from "./api.js";
import { embedTexts, loadLocalEmbedder } from "./model.js";
import {
  EVAL_QUERIES,
  FALLBACK_BATCH_SIZE,
  MODEL_SIZES,
  SAMPLE_DOCUMENTS,
} from "../shared/constants.mjs";

const $ = (selector) => document.querySelector(selector);
const elements = {
  backendBadge: $("#backendBadge"), dbBadge: $("#dbBadge"), backendNote: $("#backendNote"),
  kbId: $("#kbId"), docInput: $("#docInput"), batchSize: $("#batchSize"),
  loadModelBtn: $("#loadModelBtn"), importBtn: $("#importBtn"), searchBtn: $("#searchBtn"),
  sampleBtn: $("#sampleBtn"), newKbBtn: $("#newKbBtn"), searchInput: $("#searchInput"),
  suggestions: $("#querySuggestions"), progressLabel: $("#progressLabel"),
  progressPercent: $("#progressPercent"), progressBar: $("#progressBar"),
  statusMessage: $("#statusMessage"), docCount: $("#docCount"), modelInfo: $("#modelInfo"),
  results: $("#results"), metricLoad: $("#metricLoad"), metricEmbed: $("#metricEmbed"),
  metricIngest: $("#metricIngest"), metricQueryEmbed: $("#metricQueryEmbed"),
  metricRetrieval: $("#metricRetrieval"), metricE2e: $("#metricE2e"),
};

let embedder = null;
let modelPromise = null;
let currentKbId = localStorage.getItem("locallens.kbId") || `kb-${Date.now().toString(36)}`;
let busy = false;

function formatMs(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value < 1000) return `${value.toFixed(1)} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}
function formatBytes(bytes) { return `${(bytes / 1024 / 1024).toFixed(1)} MiB`; }
function hash32(text) {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}
function chunkText(text, maxLength = 320) {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= maxLength) return [clean];
  const chunks = [];
  for (let start = 0; start < clean.length; start += maxLength - 40) {
    chunks.push(clean.slice(start, start + maxLength));
  }
  return chunks;
}
function setProgress(percent, label) {
  const safe = Math.max(0, Math.min(100, Number(percent) || 0));
  elements.progressBar.style.width = `${safe}%`;
  elements.progressPercent.textContent = `${Math.round(safe)}%`;
  if (label) elements.progressLabel.textContent = label;
}
function setStatus(message, tone = "normal") {
  elements.statusMessage.textContent = message;
  elements.statusMessage.dataset.tone = tone;
}
function setBackend(backend) {
  if (backend.status === "loading") {
    elements.backendBadge.textContent = `加载中 · ${backend.label}`;
    elements.backendBadge.className = "badge badge-warn";
    return;
  }
  if (backend.status === "fallback") {
    elements.backendBadge.textContent = `降级到 ${backend.label}`;
    elements.backendBadge.className = "badge badge-warn";
    return;
  }
  if (backend.status === "ready") {
    elements.backendBadge.textContent = backend.label;
    elements.backendBadge.className = "badge badge-success";
    elements.backendNote.textContent = backend.webgpuAvailable
      ? "WebGPU 已启用 · FP16 本地推理"
      : "WebGPU 不可用 · 已自动降级 WASM / INT8";
    elements.metricLoad.textContent = formatMs(backend.loadMs);
    elements.modelInfo.textContent = `${backend.dtype.toUpperCase()} · ${formatBytes(
      backend.dtype === "fp16" ? MODEL_SIZES.fp16Onnx : MODEL_SIZES.int8Onnx,
    )}`;
  }
}
function setBusy(nextBusy) {
  busy = nextBusy;
  for (const button of [elements.loadModelBtn, elements.importBtn, elements.searchBtn]) {
    button.disabled = nextBusy;
  }
}
async function ensureEmbedder() {
  if (embedder) return embedder;
  if (modelPromise) return modelPromise;
  modelPromise = loadLocalEmbedder({
    onBackend: setBackend,
    onProgress: (event) => {
      if (event.status === "progress") {
        setProgress(event.progress ?? 0, `下载 ${event.file ?? "模型文件"}`);
      } else if (event.status === "ready") {
        setProgress(100, "模型已就绪");
      } else if (event.status === "initiate") {
        setProgress(2, `准备 ${event.file ?? "模型"}`);
      }
    },
  }).then((loaded) => { embedder = loaded; return loaded; })
    .catch((error) => { modelPromise = null; throw error; });
  return modelPromise;
}
function sampleText() { return SAMPLE_DOCUMENTS.map((document) => document.text).join("\n"); }
function renderSuggestions() {
  elements.suggestions.replaceChildren();
  for (const item of EVAL_QUERIES) {
    const button = document.createElement("button");
    button.className = "suggestion";
    button.type = "button";
    button.textContent = item.query;
    button.addEventListener("click", () => {
      elements.searchInput.value = item.query;
      elements.searchInput.focus();
    });
    elements.suggestions.append(button);
  }
}

function renderResults(results, query) {
  elements.results.replaceChildren();
  elements.results.className = "results";
  if (!results.length) {
    elements.results.className = "results empty-state";
    elements.results.innerHTML = "<div class=\"empty-icon\">∅</div><h3>没有检索到结果</h3><p>请先导入文档，或更换查询条件。</p>";
    return;
  }
  const title = document.createElement("div");
  title.className = "results-title";
  const titleText = document.createElement("span");
  titleText.textContent = `混合检索命中 ${results.length} 条`;
  const queryText = document.createElement("small");
  queryText.textContent = `查询：${query}`;
  title.append(titleText, queryText);
  elements.results.append(title);
  results.forEach((result, index) => {
    const article = document.createElement("article");
    article.className = "result-card";
    const head = document.createElement("div");
    head.className = "result-head";
    const rank = document.createElement("span");
    rank.className = "result-rank";
    rank.textContent = String(index + 1).padStart(2, "0");
    const meta = document.createElement("div");
    meta.className = "result-meta";
    const source = document.createElement("span");
    source.className = "source-pill";
    source.textContent = result.metadata?.source ?? "local";
    const id = document.createElement("span");
    id.textContent = result.id;
    meta.append(source, id);
    head.append(rank, meta);
    if (result.distance != null) {
      const distance = document.createElement("span");
      distance.className = "distance";
      distance.textContent = `融合距离 ${Number(result.distance).toFixed(3)}`;
      head.append(distance);
    }
    const text = document.createElement("p");
    text.textContent = result.text;
    article.append(head, text);
    elements.results.append(article);
  });
}

async function refreshStats() {
  try {
    const stats = await api.stats(currentKbId);
    elements.docCount.textContent = String(stats.count);
    elements.dbBadge.textContent = `seekdb 已连接 · ${stats.count} docs`;
    elements.dbBadge.className = "badge badge-success";
  } catch {
    elements.dbBadge.textContent = "seekdb 不可用";
    elements.dbBadge.className = "badge badge-error";
  }
}

async function loadModel() {
  if (busy) return;
  setBusy(true);
  try {
    setStatus("正在检测 WebGPU 并加载端侧模型。首次运行会下载模型。");
    await ensureEmbedder();
    setStatus("端侧 embedding 模型已就绪，可以导入文档或检索。", "success");
  } catch (error) {
    setStatus(`模型加载失败：${error.message}`, "error");
    setProgress(0, "模型加载失败");
  } finally { setBusy(false); }
}

async function importDocuments() {
  if (busy) return;
  const lines = elements.docInput.value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) { setStatus("请先输入至少一行文本。", "error"); return; }
  setBusy(true);
  try {
    const activeEmbedder = await ensureEmbedder();
    const chunks = lines.flatMap((line) => chunkText(line).map((text, chunkIndex) => ({ text, chunkIndex })));
    const documents = chunks.map((chunk, index) => ({
      id: `${currentKbId}-${hash32(chunk.text)}-${index}`,
      text: chunk.text,
      source: "browser-import",
      chunkIndex: chunk.chunkIndex,
    }));
    setProgress(1, `本地向量化 0 / ${documents.length}`);
    const embedded = await embedTexts(activeEmbedder, documents.map((document) => document.text), {
      batchSize: Number(elements.batchSize.value) || FALLBACK_BATCH_SIZE,
      onProgress: (done, total) => setProgress((done / total) * 80, `本地向量化 ${done} / ${total}`),
    });
    documents.forEach((document, index) => { document.embedding = embedded.vectors[index]; });
    setProgress(86, "写入 seekdb 并刷新索引");
    const ingestStart = performance.now();
    const result = await api.addDocuments(currentKbId, documents);
    const ingestWallMs = performance.now() - ingestStart;
    setProgress(100, "写入与索引刷新完成");
    elements.metricEmbed.textContent = `${formatMs(embedded.elapsedMs)} · ${embedded.throughput.toFixed(1)} docs/s`;
    elements.metricIngest.textContent = formatMs(result.writeMs + result.refreshMs);
    elements.docCount.textContent = String(result.count);
    elements.dbBadge.textContent = `seekdb 已连接 · ${result.count} docs`;
    elements.dbBadge.className = "badge badge-success";
    setStatus(`已导入 ${documents.length} 个文本块；写入 ${result.writeMs.toFixed(1)} ms，索引刷新 ${result.refreshMs.toFixed(1)} ms（总墙钟 ${ingestWallMs.toFixed(1)} ms）。`, "success");
  } catch (error) {
    setStatus(`导入失败：${error.message}`, "error");
  } finally { setBusy(false); }
}

async function search() {
  if (busy) return;
  const query = elements.searchInput.value.trim();
  if (!query) { setStatus("请输入检索问题。", "error"); return; }
  setBusy(true);
  const started = performance.now();
  try {
    const activeEmbedder = await ensureEmbedder();
    const queryEmbedStart = performance.now();
    const embedded = await embedTexts(activeEmbedder, [query], { batchSize: 1 });
    const queryEmbedMs = performance.now() - queryEmbedStart;
    const result = await api.search(currentKbId, query, embedded.vectors[0], 5);
    const e2eMs = performance.now() - started;
    elements.metricQueryEmbed.textContent = formatMs(queryEmbedMs);
    elements.metricRetrieval.textContent = formatMs(result.retrievalMs);
    elements.metricE2e.textContent = formatMs(e2eMs);
    renderResults(result.results, query);
    setStatus(`查询向量在本地生成；seekdb 使用向量 + 全文混合检索返回 ${result.results.length} 条结果。`, "success");
  } catch (error) {
    renderResults([], query);
    setStatus(`检索失败：${error.message}`, "error");
  } finally { setBusy(false); }
}

function switchKnowledgeBase(nextId) {
  currentKbId = nextId;
  localStorage.setItem("locallens.kbId", nextId);
  elements.kbId.value = nextId;
  elements.results.className = "results empty-state";
  elements.results.innerHTML = "<div class=\"empty-icon\">⌁</div><h3>已切换知识库</h3><p>导入文档或输入查询开始使用。</p>";
  refreshStats();
}

async function initialize() {
  elements.kbId.value = currentKbId;
  elements.docInput.value = sampleText();
  renderSuggestions();
  setProgress(0, "等待加载模型");
  elements.modelInfo.textContent = `INT8 ${formatBytes(MODEL_SIZES.int8Onnx)} / FP16 ${formatBytes(MODEL_SIZES.fp16Onnx)}`;
  elements.loadModelBtn.addEventListener("click", loadModel);
  elements.importBtn.addEventListener("click", importDocuments);
  elements.searchBtn.addEventListener("click", search);
  elements.sampleBtn.addEventListener("click", () => {
    elements.docInput.value = sampleText();
    setStatus("示例语料已载入，可以直接向量化并写入 seekdb。");
  });
  elements.newKbBtn.addEventListener("click", () => switchKnowledgeBase(`kb-${Date.now().toString(36)}`));
  elements.kbId.addEventListener("change", () => {
    const next = elements.kbId.value.trim().toLowerCase();
    if (!/^[a-z0-9][a-z0-9-]{0,31}$/.test(next)) {
      setStatus("知识库 ID 只能包含小写字母、数字和连字符，长度不超过 32。", "error");
      elements.kbId.value = currentKbId;
      return;
    }
    switchKnowledgeBase(next);
  });
  elements.searchInput.addEventListener("keydown", (event) => { if (event.key === "Enter") search(); });
  try {
    const health = await api.health();
    elements.dbBadge.textContent = `seekdb 已连接 · ${health.seekdb}`;
    elements.dbBadge.className = "badge badge-success";
  } catch {
    elements.dbBadge.textContent = "seekdb 未连接";
    elements.dbBadge.className = "badge badge-error";
  }
  refreshStats();
}

initialize();
