import path from "node:path";
import { seekdb as seekdbEngine } from "@oceanbase/seekdb-node";
import {
  FulltextIndexConfig,
  Schema,
  SeekdbClient,
  VectorIndexConfig,
} from "seekdb";

const VECTOR_DIMENSION = 512;
const COLLECTION_PREFIX = "local_rag_";

function sanitizeKbId(value) {
  const id = String(value ?? "").trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9-]{0,31}$/.test(id)) {
    throw new Error("knowledge base id must match [a-z0-9][a-z0-9-]{0,31}");
  }
  return id;
}

export class LocalKnowledgeBase {
  constructor(engine, client, dbPath) {
    this.engine = engine;
    this.client = client;
    this.dbPath = dbPath;
    this.collections = new Map();
  }

  static async create(dbPath = path.resolve("data", "seekdb-rag")) {
    const engine = await seekdbEngine.open(dbPath);
    const endpoint = engine.connectionOptions();
    const client = new SeekdbClient({
      host: endpoint.host,
      port: endpoint.port,
      user: endpoint.user,
      password: "",
      database: "test",
    });
    return new LocalKnowledgeBase(engine, client, dbPath);
  }

  async getCollection(kbId) {
    const safeId = sanitizeKbId(kbId);
    const name = `${COLLECTION_PREFIX}${safeId.replaceAll("-", "_")}`;
    if (this.collections.has(name)) return this.collections.get(name);

    const schema = new Schema({
      fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
      vectorIndex: new VectorIndexConfig({
        hnsw: { dimension: VECTOR_DIMENSION, distance: "cosine" },
        embeddingFunction: null,
      }),
    });

    let collection;
    try {
      collection = await this.client.getCollection({ name, embeddingFunction: null });
    } catch {
      collection = await this.client.createCollection({ name, schema });
    }
    this.collections.set(name, collection);
    return collection;
  }

  async upsertDocuments(kbId, documents) {
    const collection = await this.getCollection(kbId);
    const writeStart = performance.now();
    await collection.upsert({
      ids: documents.map((document) => document.id),
      documents: documents.map((document) => document.text),
      embeddings: documents.map((document) => document.embedding),
      metadatas: documents.map((document) => ({
        doc_id: document.id,
        source: document.source ?? "manual",
        chunk_index: document.chunkIndex ?? 0,
        imported_at: new Date().toISOString(),
      })),
    });
    const writeMs = performance.now() - writeStart;
    const refreshStart = performance.now();
    await collection.refresh_index();
    const refreshMs = performance.now() - refreshStart;
    return { writeMs, refreshMs, count: await collection.count() };
  }

  async search(kbId, query, queryEmbedding, nResults = 5) {
    const collection = await this.getCollection(kbId);
    const started = performance.now();
    const result = await collection.hybridSearch({
      query: { whereDocument: { $contains: query } },
      knn: { queryEmbeddings: [queryEmbedding] },
      nResults,
      include: ["documents", "metadatas", "distances"],
    });
    const retrievalMs = performance.now() - started;
    const ids = result.ids?.[0] ?? [];
    const documents = result.documents?.[0] ?? [];
    const metadatas = result.metadatas?.[0] ?? [];
    const distances = result.distances?.[0] ?? [];
    return {
      retrievalMs,
      results: ids.map((id, index) => ({
        id,
        text: documents[index] ?? "",
        metadata: metadatas[index] ?? {},
        distance: distances[index] ?? null,
      })),
    };
  }

  async stats(kbId) {
    const collection = await this.getCollection(kbId);
    return { count: await collection.count(), collection: collection.name };
  }

  async close() {
    await this.client.close();
    await this.engine.close();
  }
}

export { VECTOR_DIMENSION, sanitizeKbId };
