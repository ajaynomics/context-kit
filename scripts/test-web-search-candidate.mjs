import assert from "node:assert/strict";

import { probeMcp, rpc } from "../docker/web-search/mcp-probe.mjs";

const url = process.argv[2];
if (!url) throw new Error("usage: node scripts/test-web-search-candidate.mjs <mcp-url>");

await probeMcp(url, { timeoutMs: 10_000 });

function payload(result) {
  const text = (result.content || []).find(part => part.type === "text")?.text;
  return text ? JSON.parse(text) : result.structuredContent;
}

const search = payload(await rpc(url, 3, "tools/call", {
  name: "search_web",
  arguments: { q: "candidate diagnostic fixture", limit: 3, provider: "searxng" }
}, 30_000));
assert.equal(search.items[0].title, "Deterministic Search Result");
assert.equal(search.providerUsed, "searxng");
assert.equal(search.diagnostics.attempts[0].status, "success");
assert.equal(search.diagnostics.attempts[0].result_count, 1);

const httpFetch = payload(await rpc(url, 4, "tools/call", {
  name: "fetch_url",
  arguments: { url: "http://mock-search.test:8080/dynamic", engine: "http", format: "text" }
}, 30_000));
assert(!httpFetch.content.includes("BROWSER_RENDERED_MARKER"));

const browserFetch = payload(await rpc(url, 5, "tools/call", {
  name: "fetch_url",
  arguments: { url: "http://mock-search.test:8080/dynamic", engine: "browser", format: "text", timeout_ms: 20_000 }
}, 60_000));
assert(browserFetch.content.includes("BROWSER_RENDERED_MARKER"));

const blocked = await rpc(url, 6, "tools/call", {
  name: "fetch_url",
  arguments: { url: "http://127.0.0.1:8765/private", engine: "browser" }
}, 30_000);
assert.equal(blocked.isError, true);
assert((blocked.content || []).some(part => part.text?.includes("Blocked localhost/private URL")));

const blockedRedirect = await rpc(url, 7, "tools/call", {
  name: "fetch_url",
  arguments: { url: "http://mock-search.test:8080/redirect-private", engine: "browser" }
}, 30_000);
assert.equal(blockedRedirect.isError, true);

await rpc(url, 8, "tools/call", {
  name: "fetch_url",
  arguments: { url: "http://mock-search.test:8080/websocket-attempt", engine: "browser", fresh: true }
}, 30_000);
const websocketCount = payload(await rpc(url, 9, "tools/call", {
  name: "fetch_url",
  arguments: { url: "http://mock-search.test:8080/ws-count", engine: "http", format: "text", fresh: true }
}, 30_000));
assert.equal(websocketCount.content.trim(), "0");

console.log("pass web-search candidate diagnostics, browser rendering, and SSRF rejection");
