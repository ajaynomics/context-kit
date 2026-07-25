import assert from "node:assert/strict";

import { probeMcp, rpc } from "../docker/web-search/mcp-probe.mjs";

const url = process.argv[2];
if (!url) throw new Error("usage: node scripts/test-docs-candidate.mjs <mcp-url>");

const required = ["docs_query", "docs_rebuild", "docs_refresh", "docs_sources"];
const tools = await probeMcp(url, { timeoutMs: 10_000, expectedTools: required });
assert.deepEqual(tools, required);

function structured(result) {
  if (result.structuredContent) return result.structuredContent;
  const text = (result.content || []).find(part => part.type === "text")?.text;
  return text ? JSON.parse(text) : null;
}

const refreshed = structured(await rpc(url, 3, "tools/call", {
  name: "docs_refresh",
  arguments: { force: true }
}, 120_000));
assert.equal(refreshed.sources[0].status, "updated", JSON.stringify(refreshed.sources[0]));
assert(refreshed.sources[0].document_count >= 2);

const search = structured(await rpc(url, 4, "tools/call", {
  name: "docs_query",
  arguments: { query: "CONTEXT_KIT_EXACT_IDENTIFIER_20260724", limit: 3 }
}, 30_000));
assert.equal(search.search_results[0].title, "Environment Variables");
assert.deepEqual(search.retrieved_content, {});

const identifier = search.search_results[0].id;
const retrieved = structured(await rpc(url, 5, "tools/call", {
  name: "docs_query",
  arguments: {
    query: "CONTEXT_KIT_EXACT_IDENTIFIER_20260724",
    retrieve_ids: [identifier],
    max_bytes: 12_000
  }
}, 30_000));
assert(retrieved.retrieved_content[identifier].content.includes("CONTEXT_KIT_EXACT_IDENTIFIER_20260724"));

console.log("pass docs candidate transport, refresh, hybrid search, and explicit retrieval");
