import { rpc } from "../docker/web-search/mcp-probe.mjs";

const [url, ...sources] = process.argv.slice(2);
if (!url) throw new Error("usage: node scripts/docs-rebuild.mjs <mcp-url> [source ...]");

await rpc(url, 1, "initialize", {
  protocolVersion: "2024-11-05",
  capabilities: {},
  clientInfo: { name: "context-kit-docs-rebuild", version: "1" }
}, 10_000);
const result = await rpc(url, 2, "tools/call", {
  name: "docs_rebuild",
  arguments: sources.length ? { sources } : {}
}, 600_000);
if (result.isError) {
  const text = (result.content || []).map(part => part.text || "").join("\n");
  throw new Error(text || "docs_rebuild failed");
}
const structured = result.structuredContent || JSON.parse(
  (result.content || []).find(part => part.type === "text")?.text || "{}"
);
console.log(JSON.stringify(structured, null, 2));
