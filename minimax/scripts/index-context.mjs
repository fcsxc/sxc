import fs from "node:fs/promises";
import path from "node:path";
import { withSeekdb, seekdbPath } from "../lib/seekdb.mjs";

const root = process.cwd();
const manifest = JSON.parse(await fs.readFile(path.join(root, "context-manifest.json"), "utf8"));

const result = await withSeekdb(async ({ connection, endpoint }) => {
  await connection.query("DELETE FROM engineering_docs");
  const now = new Date();
  for (const doc of manifest.documents) {
    const content = await fs.readFile(path.join(root, doc.path), "utf8");
    await connection.execute(
      `INSERT INTO engineering_docs
       (id, kind, path, symbol, content, version, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [doc.id, doc.kind, doc.path, doc.symbol ?? null, content, doc.version, now],
    );
  }
  const [rows] = await connection.query(
    "SELECT id, kind, path, symbol, version, CHAR_LENGTH(content) AS chars, updated_at FROM engineering_docs ORDER BY kind, id",
  );
  return rows;
});

console.log(JSON.stringify({
  ok: true,
  database: "seekdb",
  seekdbPath: seekdbPath(),
  manifestVersion: manifest.version,
  indexed: result,
}, null, 2));
