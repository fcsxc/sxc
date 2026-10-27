import { powerContextPost, powerContextUrl } from "../lib/powercontext.mjs";

const suffix = new Date().toISOString().replace(/[:.]/g, "-");
const scope = await powerContextPost("/v1/scopes", {
  title: "SDD engineering context demo",
  summary: "MiniMax + seekdb + PowerContext task state",
  idempotency_key: process.env.SCOPE_IDEMPOTENCY_KEY ?? `sdd-context-${suffix}`,
});
console.log(JSON.stringify({ provider: "PowerContext", endpoint: powerContextUrl(), ...scope }, null, 2));
