import { seekdb } from "@oceanbase/seekdb-node";
import { SeekdbClient, Schema, FulltextIndexConfig, VectorIndexConfig } from "seekdb";

const db = await seekdb.open(`./data/seekdb-smoke-${Date.now()}`);
const endpoint = db.connectionOptions();
let client;
try {
  client = new SeekdbClient({
    host: endpoint.host,
    port: endpoint.port,
    user: endpoint.user,
    password: "",
    database: "test",
  });
  const schema = new Schema({
    fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
    vectorIndex: new VectorIndexConfig({
      hnsw: { dimension: 4, distance: "cosine" },
      embeddingFunction: null,
    }),
  });
  const collection = await client.createCollection({ name: "smoke_docs", schema });
  await collection.add({
    ids: ["a", "b"],
    documents: ["seekdb 混合检索 数据库", "浏览器 本地向量 推理"],
    embeddings: [[1, 0, 0, 0], [0, 1, 0, 0]],
    metadatas: [{ topic: "db" }, { topic: "browser" }],
  });
  await collection.refresh_index();
  const result = await collection.hybridSearch({
    query: { whereDocument: { $contains: "数据库" } },
    knn: { queryEmbeddings: [[1, 0, 0, 0]] },
    nResults: 3,
    include: ["documents", "metadatas", "distances"],
  });
  console.log(JSON.stringify({ endpoint, result, count: await collection.count() }, null, 2));
} finally {
  if (client) await client.close();
  db.close();
}
