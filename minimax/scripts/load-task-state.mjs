import { powerContextPost, powerContextUrl } from "../lib/powercontext.mjs";

const args = process.argv.slice(2);
function option(name, fallback = "") {
  const index = args.indexOf(`--${name}`);
  return index >= 0 ? args[index + 1] ?? fallback : fallback;
}
const scope = option("scope", process.env.POWERCONTEXT_SCOPE);
if (!scope) {
  console.error("Missing --scope or POWERCONTEXT_SCOPE");
  process.exit(2);
}
const query = option("query", "current SDD task progress and verification");
const prepared = await powerContextPost("/v1/context/prepare", {
  scope_id: scope,
  query,
  max_bytes: 4000,
});
console.log(JSON.stringify({
  provider: "PowerContext",
  endpoint: powerContextUrl(),
  scope,
  query,
  status: prepared.status,
  content: prepared.content ?? "",
}, null, 2));
