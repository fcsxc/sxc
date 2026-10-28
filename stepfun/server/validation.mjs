const VECTOR_DIMENSION = 512;

export function validateEmbedding(value, label = "embedding") {
  if (!Array.isArray(value) || value.length !== VECTOR_DIMENSION) {
    throw new Error(`${label} must be an array of ${VECTOR_DIMENSION} numbers`);
  }
  for (const number of value) {
    if (typeof number !== "number" || !Number.isFinite(number)) {
      throw new Error(`${label} contains a non-finite value`);
    }
  }
  return value;
}

export function normalizeDocuments(input) {
  if (!Array.isArray(input) || input.length === 0) {
    throw new Error("documents must be a non-empty array");
  }
  if (input.length > 100) {
    throw new Error("at most 100 documents can be imported at once");
  }
  return input.map((document, index) => {
    const id = String(document?.id ?? "").trim();
    const text = String(document?.text ?? "").trim();
    if (!id || id.length > 128) throw new Error(`documents[${index}].id is invalid`);
    if (!text || text.length > 4000) throw new Error(`documents[${index}].text is invalid`);
    validateEmbedding(document?.embedding, `documents[${index}].embedding`);
    return {
      id,
      text,
      embedding: document.embedding,
      source: String(document?.source ?? "manual").slice(0, 80),
      chunkIndex: Number.isInteger(document?.chunkIndex) ? document.chunkIndex : 0,
    };
  });
}
