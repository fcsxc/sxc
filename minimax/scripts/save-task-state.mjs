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
const state = {
  task: option("task", "Add text filtering to filterTickets"),
  status: option("status", "in_progress"),
  completed: option("completed", "Context assembled from seekdb."),
  pending: option("pending", "Implement filters.text in business/ticket-service.js."),
  verification: option("verification", "Target test currently failing; regression tests passing."),
};
const text = `SDD_TASK_STATE\n${JSON.stringify(state, null, 2)}`;
const saved = await powerContextPost("/v1/memory/remember", {
  scope_id: scope,
  kind: "decision",
  text,
  reason: "SDD context module task checkpoint",
});
console.log(JSON.stringify({ provider: "PowerContext", endpoint: powerContextUrl(), scope, state, saved }, null, 2));
