import { chromium } from "playwright-core";
import fs from "node:fs/promises";

const edge = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const browser = await chromium.launch({
  executablePath: edge,
  headless: true,
  args: ["--no-sandbox", "--disable-gpu", "--disable-gpu-sandbox", "--disable-features=WebGPU"],
});
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await context.newPage();
const consoleErrors = [];
const requestFailures = [];
const httpErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("requestfailed", (request) => {
  requestFailures.push({ url: request.url(), error: request.failure()?.errorText ?? "unknown" });
});
page.on("response", (response) => {
  if (response.status() >= 400) httpErrors.push({ url: response.url(), status: response.status() });
});
const result = { startedAt: new Date().toISOString(), browser: "Edge headless", consoleErrors, requestFailures, httpErrors };
try {
  await page.goto("http://127.0.0.1:8787", { waitUntil: "networkidle", timeout: 120000 });
  await page.getByRole("button", { name: "加载端侧模型" }).click();
  await page.waitForFunction(
    () => /^(WebGPU · FP16|WASM · INT8)$/.test((document.querySelector("#backendBadge")?.textContent ?? "").trim()),
    null,
    { timeout: 300000 },
  );
  result.backend = (await page.locator("#backendBadge").textContent()).trim();
  result.backendNote = (await page.locator("#backendNote").textContent()).trim();
  await page.getByRole("button", { name: "向量化并写入 seekdb" }).click();
  await page.waitForFunction(() => {
    const node = document.querySelector("#statusMessage");
    const text = node?.textContent ?? "";
    return text.includes("已导入") || node?.dataset.tone === "error";
  }, null, { timeout: 300000 });
  if ((await page.locator("#statusMessage").getAttribute("data-tone")) === "error") {
    throw new Error((await page.locator("#statusMessage").textContent()).trim());
  }
  result.importStatus = (await page.locator("#statusMessage").textContent()).trim();
  result.docCount = (await page.locator("#docCount").textContent()).trim();
  await page.locator("#searchInput").fill("怎样让新文档马上能搜到？");
  await page.getByRole("button", { name: "混合检索", exact: true }).click();
  await page.waitForFunction(() => {
    const node = document.querySelector("#statusMessage");
    return document.querySelectorAll(".result-card").length > 0 || node?.dataset.tone === "error";
  }, null, { timeout: 180000 });
  if ((await page.locator("#statusMessage").getAttribute("data-tone")) === "error") {
    throw new Error((await page.locator("#statusMessage").textContent()).trim());
  }
  result.resultCount = await page.locator(".result-card").count();
  result.firstResult = (await page.locator(".result-card p").first().textContent()).trim();
  result.metrics = {
    load: (await page.locator("#metricLoad").textContent()).trim(),
    embed: (await page.locator("#metricEmbed").textContent()).trim(),
    ingest: (await page.locator("#metricIngest").textContent()).trim(),
    queryEmbed: (await page.locator("#metricQueryEmbed").textContent()).trim(),
    retrieval: (await page.locator("#metricRetrieval").textContent()).trim(),
    e2e: (await page.locator("#metricE2e").textContent()).trim(),
  };
  await page.screenshot({ path: "evidence/browser-wasm.png", fullPage: true });
  result.ok = true;
} catch (error) {
  result.ok = false;
  result.error = error.message;
  await page.screenshot({ path: "evidence/browser-wasm-error.png", fullPage: true }).catch(() => {});
} finally {
  result.endedAt = new Date().toISOString();
  await fs.writeFile("evidence/browser-wasm-result.json", JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
}