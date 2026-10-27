import fs from "node:fs/promises";
import path from "node:path";

const version = process.argv[2];
if (!["v1", "v2"].includes(version)) {
  console.error("Usage: node scripts/use-spec-version.mjs v1|v2");
  process.exit(2);
}
const root = process.cwd();
const manifestPath = path.join(root, "context-manifest.json");
const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
const source = path.join(root, "specs", "history", `ticket-filter-${version}.md`);
const current = path.join(root, "specs", "ticket-filter.md");
await fs.copyFile(source, current);
manifest.version = version;
for (const document of manifest.documents) {
  if (document.kind === "spec") {
    document.id = `spec-ticket-filter-${version}`;
    document.version = version;
  }
}
await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ ok: true, specVersion: version, current: "specs/ticket-filter.md" }, null, 2));
