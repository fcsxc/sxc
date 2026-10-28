import test from "node:test";
import assert from "node:assert/strict";
import { normalizeDocuments, validateEmbedding } from "../server/validation.mjs";

const vector = Array.from({ length: 512 }, (_, index) => (index === 0 ? 1 : 0));

test("validates 512-dimensional finite embeddings", () => {
  assert.equal(validateEmbedding(vector).length, 512);
  assert.throws(() => validateEmbedding([1, 2, 3]), /512/);
  assert.throws(() => validateEmbedding(Array.from({ length: 512 }, () => Number.NaN)), /finite/);
});

test("normalizes a valid document batch", () => {
  const documents = normalizeDocuments([
    { id: "doc-1", text: "local embedding", embedding: vector, source: "test" },
  ]);
  assert.equal(documents.length, 1);
  assert.equal(documents[0].id, "doc-1");
  assert.equal(documents[0].chunkIndex, 0);
});

test("rejects empty and oversized batches", () => {
  assert.throws(() => normalizeDocuments([]), /non-empty/);
  const batch = Array.from({ length: 101 }, (_, index) => ({
    id: `doc-${index}`,
    text: "text",
    embedding: vector,
  }));
  assert.throws(() => normalizeDocuments(batch), /100/);
});
