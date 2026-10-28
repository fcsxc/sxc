import path from "node:path";
import process from "node:process";
import { createServer as createViteServer } from "vite";
import { createApp } from "./app.mjs";
import { LocalKnowledgeBase } from "./db.mjs";

const production = process.argv.includes("--production");
const port = Number(process.env.PORT ?? 8787);
const dbPath = path.resolve(process.env.SEEKDB_PATH ?? path.join("data", "seekdb-rag"));

const runtime = await LocalKnowledgeBase.create(dbPath);
const vite = production
  ? null
  : await createViteServer({ server: { middlewareMode: true }, appType: "spa" });
const app = createApp({ runtime, vite, production });
const server = app.listen(port, "127.0.0.1", () => {
  console.log(`LocalLens running at http://127.0.0.1:${port}`);
  console.log(`seekdb data: ${dbPath}`);
});

async function shutdown() {
  server.close();
  await runtime.close();
  if (vite) await vite.close();
  process.exit(0);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
