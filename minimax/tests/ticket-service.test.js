import test from "node:test";
import assert from "node:assert/strict";
import { filterTickets } from "../business/ticket-service.js";

const tickets = [
  { id: "T1", title: "VPN login fails", description: "Remote access error", status: "open", priority: 4 },
  { id: "T2", title: "Invoice export", description: "Billing download", status: "open", priority: 2 },
  { id: "T3", title: "Account review", description: "VPN permissions need cleanup", status: "closed", priority: 3 },
  { id: "T4", title: "Printer setup", description: "Office printer", status: "open", priority: 1 },
];

test("existing status filter remains compatible", () => {
  assert.deepEqual(filterTickets(tickets, { status: "open" }).map((t) => t.id), ["T1", "T2", "T4"]);
});

test("existing minPriority filter remains inclusive", () => {
  assert.deepEqual(filterTickets(tickets, { minPriority: 3 }).map((t) => t.id), ["T1", "T3"]);
});

test("target: text matches title and description case-insensitively", () => {
  assert.deepEqual(filterTickets(tickets, { text: "  vpn  " }).map((t) => t.id), ["T1", "T3"]);
});

test("target: blank text does not filter out tickets", () => {
  assert.deepEqual(filterTickets(tickets, { text: "   " }).map((t) => t.id), ["T1", "T2", "T3", "T4"]);
});

test("all existing filters can be combined with text", () => {
  assert.deepEqual(
    filterTickets(tickets, { status: "open", minPriority: 2, text: "vpn" }).map((t) => t.id),
    ["T1"],
  );
});
