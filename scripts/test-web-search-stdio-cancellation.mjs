import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";

import {
  McpSmokeClient,
  requireToolSuccess,
  textFrom
} from "./mcp-smoke-client.mjs";

const command = process.argv[2];
const args = process.argv.slice(3);
if (!command) throw new Error("usage: node scripts/test-web-search-stdio-cancellation.mjs <command> [args...]");

const client = new McpSmokeClient({
  command,
  args,
  tmpPrefix: "context-kit-stdio-cancellation-"
});

function payload(result) {
  const text = textFrom(requireToolSuccess("fetch_url", result));
  return JSON.parse(text);
}

async function slowCount() {
  const result = await client.callTool("fetch_url", {
    url: "http://mock-search.test:8080/slow-count",
    engine: "http",
    format: "text",
    fresh: true
  });
  return Number(payload(result).content.trim());
}

async function waitForSlowCount(expected, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let actual;
  while (Date.now() < deadline) {
    actual = await slowCount();
    if (actual === expected) return;
    await delay(50);
  }
  assert.equal(actual, expected, `stdio slow request count did not reach ${expected}`);
}

try {
  await client.initialize({ name: "context-kit-stdio-cancellation", version: "1" });
  const requestId = client.nextId;
  const pendingFetch = client.callTool("fetch_url", {
    url: "http://mock-search.test:8080/slow",
    engine: "browser",
    format: "text",
    fresh: true,
    timeout_ms: 120_000
  });
  await waitForSlowCount(1, 10_000);
  client.notify("notifications/cancelled", {
    requestId,
    reason: "stdio client disconnected"
  });
  await assert.rejects(pendingFetch, /cancel/i);
  await waitForSlowCount(0, 3_000);
  console.log("pass web-search stdio bridge cancellation");
} finally {
  await client.stop();
}
