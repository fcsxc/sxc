import fs from "node:fs/promises";
import path from "node:path";

const responsePath = path.resolve(process.argv[2] ?? "records/minimax-response.md");
const targetPath = path.resolve(process.argv[3] ?? "business/ticket-service.js");
const response = await fs.readFile(responsePath, "utf8");
const match = response.match(/```(?:javascript|js)\s*\n([\s\S]*?)\n```/i);
if (!match) {
  throw new Error("MiniMax response did not contain a JavaScript fenced code block");
}
await fs.writeFile(targetPath, `${match[1].trim()}\n`, "utf8");
console.log(JSON.stringify({ ok: true, responsePath, targetPath, appliedChars: match[1].trim().length }, null, 2));
