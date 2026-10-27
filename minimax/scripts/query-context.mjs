import fs from "node:fs/promises";
import path from "node:path";
import { withSeekdb, seekdbPath } from "../lib/seekdb.mjs";
import { powerContextPost, powerContextUrl } from "../lib/powercontext.mjs";

const task = process.argv.slice(2).join(" ").trim();
if (!task) {
  console.error("Usage: node scripts/query-context.mjs <development task>");
  process.exit(2);
}
const root = process.cwd();
const manifest = JSON.parse(await fs.readFile(path.join(root, "context-manifest.json"), "utf8"));

function taskTokens(text) {
  const normalized = text.toLowerCase();
  const words = normalized.match(/[a-z0-9_]+/g) ?? [];
  const stop = new Set(["the", "and", "for", "with", "must", "keep", "add", "filter", "filters"]);
  const values = new Set(words.filter((word) => word.length > 1 && !stop.has(word)));
  for (const run of normalized.match(/[\u4e00-\u9fff]{2,}/g) ?? []) {
    values.add(run);
    for (let index = 0; index < run.length - 1; index += 1) {
      values.add(run.slice(index, index + 2));
    }
  }
  return [...values];
}

const tokens = taskTokens(task);
const documents = await withSeekdb(async ({ connection, endpoint }) => {
  const [rows] = await connection.query(
    "SELECT id, kind, path, symbol, content, version FROM engineering_docs ORDER BY kind, id",
  );
  return rows.map((row) => {
    const haystack = `${row.path} ${row.symbol ?? ""}\n${row.content}`.toLowerCase();
    const matchedTerms = tokens.filter((token) => haystack.includes(token));
    const score = matchedTerms.reduce((total, token) => total + (token.length > 3 ? 2 : 1), 0);
    return { ...row, endpoint, matchedTerms, score };
  });
});

const ranked = documents
  .filter((document) => document.score > 0)
  .sort((left, right) => right.score - left.score || left.kind.localeCompare(right.kind));

const byKind = (kind) => ranked
  .filter((document) => document.kind === kind)
  .map((document) => ({
    source: document.path,
    symbol: document.symbol,
    version: document.version,
    matchedTerms: document.matchedTerms,
    content: document.content,
  }));

let taskState = null;
const scopeId = process.env.POWERCONTEXT_SCOPE;
if (scopeId) {
  const prepared = await powerContextPost("/v1/context/prepare", {
    scope_id: scopeId,
    query: `SDD_TASK_STATE filterTickets text filtering seekdb PowerContext ${task}`,
    max_bytes: 4000,
  });
  taskState = {
    provider: "PowerContext",
    endpoint: powerContextUrl(),
    scopeId,
    status: prepared.status,
    content: prepared.content ?? "",
  };
}

console.log(JSON.stringify({
  ok: true,
  task,
  contextVersion: manifest.version,
  database: {
    engine: "seekdb",
    path: seekdbPath(),
    query: "SELECT id, kind, path, symbol, content, version FROM engineering_docs",
    matchedDocuments: ranked.length,
  },
  sourceKinds: Object.fromEntries(["spec", "code", "test"].map((kind) => [
    kind,
    ranked.filter((document) => document.kind === kind).length,
  ])),
  specs: byKind("spec"),
  code: byKind("code"),
  tests: byKind("test"),
  taskState,
}, null, 2));
