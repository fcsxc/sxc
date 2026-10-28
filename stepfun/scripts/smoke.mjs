import { SeekdbClient, Schema, FulltextIndexConfig, VectorIndexConfig } from "seekdb";

const path = `./data/smoke-db-${Date.now()}`;
const client = new SeekdbClient({ path, database: "test" });
try {
  const schema = new Schema({
    fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
    vectorIndex: new VectorIndexConfig({ hnsw: { dimension: 4, distance: "cosine" }, embeddingFunction: null }),
  });
  const collection = await client.createCollection({ name: "smoke_docs", schema });
  await collection.add({
    ids: ["a", "b"],
    documents: ["seekdb 混合检索 数据库", "浏览器 本地向量 推理"],
    embeddings: [[1,0,0,0],[0,1,0,0]],
    metadatas: [{topic:"db"},{topic:"browser"}],
  });
  await collection.refresh_index();
  const result = await collection.hybridSearch({
    query: { whereDocument: { $contains: "数据库" } },
    knn: { queryEmbeddings: [[1,0,0,0]] },
    nResults: 3,
    include: ["documents", "metadatas", "distances"],
  });
  console.log(JSON.stringify(result, null, 2));
  console.log("count", await collection.count());
} finally {
  await client.close();
}
