import express from "express";
import path from "node:path";
import { normalizeDocuments, validateEmbedding } from "./validation.mjs";

export function createApp({ runtime, vite, production = false }) {
  const app = express();
  app.use(express.json({ limit: "8mb" }));

  app.get("/api/health", (req, res) => {
    res.json({
      ok: true,
      seekdb: "@seekdb/js 1.4.0",
      engine: "@oceanbase/seekdb-node 1.4.0",
      mode: "local server",
    });
  });

  app.get("/api/kb/:kbId/stats", async (req, res, next) => {
    try {
      res.json(await runtime.stats(req.params.kbId));
    } catch (error) {
      next(error);
    }
  });

  app.post("/api/kb/:kbId/documents", async (req, res, next) => {
    try {
      const documents = normalizeDocuments(req.body?.documents);
      const result = await runtime.upsertDocuments(req.params.kbId, documents);
      res.json({ ok: true, ...result });
    } catch (error) {
      next(error);
    }
  });

  app.post("/api/kb/:kbId/search", async (req, res, next) => {
    try {
      const query = String(req.body?.query ?? "").trim();
      if (!query) throw new Error("query is required");
      const embedding = validateEmbedding(req.body?.queryEmbedding, "queryEmbedding");
      const nResults = Math.min(Math.max(Number(req.body?.nResults ?? 5), 1), 10);
      res.json({
        ok: true,
        ...(await runtime.search(req.params.kbId, query, embedding, nResults)),
      });
    } catch (error) {
      next(error);
    }
  });

  if (vite) {
    app.use(vite.middlewares);
  } else if (production) {
    const dist = path.resolve("dist");
    app.use(express.static(dist));
    app.get(/.*/, (req, res) => res.sendFile(path.join(dist, "index.html")));
  }

  app.use((error, req, res, next) => {
    if (res.headersSent) return next(error);
    const status = /invalid|required|must|at most|id /.test(error.message) ? 400 : 500;
    res.status(status).json({ ok: false, error: error.message });
  });

  return app;
}
