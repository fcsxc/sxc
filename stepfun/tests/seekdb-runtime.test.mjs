import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { LocalKnowledgeBase } from "../server/db.mjs";

const dimension = 512;
function vector(first, second = 0) {
  const values = Array.from({ length: dimension }, () => 0);
  values[0] = first;
  values[1] = second;
  return values;
}

test("seekdb-js performs hybrid retrieval after refresh", async () => {
  const dbPath = path.resolve("data", `seekdb-test-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  const runtime = await LocalKnowledgeBase.create(dbPath);
  try {
    const inserted = await runtime.upsertDocuments("test-kb", [
      { id: "doc-a", text: "seekdb 混合检索会融合向量和全文结果", embedding: vector(1), source: "test" },
      { id: "doc-b", text: "浏览器本地运行 embedding 模型", embedding: vector(0, 1), source: "test" },
      { id: "doc-c", text: "索引刷新之后新增文档可以立即检索", embedding: vector(0.8, 0.2), source: "test" },
    ]);
    assert.equal(inserted.count, 3);
    const result = await runtime.search("test-kb", "索引刷新", vector(1), 3);
    assert.ok(result.results.length > 0);
    assert.ok(result.results.some((item) => item.id === "doc-c"));
    assert.ok(result.retrievalMs > 0);
  } finally {
    await runtime.close();
  }
});
