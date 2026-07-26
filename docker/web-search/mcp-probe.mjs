import { fileURLToPath } from "node:url";

const protocolVersion = "2024-11-05";
const expectedTools = ["fetch_url", "search_web"];

export async function rpc(url, id, method, params = {}, timeoutMs = 5000, signal) {
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
      "MCP-Protocol-Version": protocolVersion
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
    signal: signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${method} returned HTTP ${response.status}: ${text.slice(0, 300)}`);

  let payload;
  if (response.headers.get("content-type")?.includes("text/event-stream")) {
    const data = text.split("\n").find(line => line.startsWith("data: "))?.slice(6);
    if (!data) throw new Error(`${method} returned an empty event stream`);
    payload = JSON.parse(data);
  } else {
    payload = JSON.parse(text);
  }
  if (payload.error) throw new Error(`${method} returned ${JSON.stringify(payload.error)}`);
  return payload.result;
}

export async function probeMcp(url, { timeoutMs = 5000, expectedTools: requiredTools = expectedTools } = {}) {
  const initialized = await rpc(url, 1, "initialize", {
    protocolVersion,
    capabilities: {},
    clientInfo: { name: "context-kit-health", version: "1" }
  }, timeoutMs);
  if (!initialized?.serverInfo?.name) throw new Error("initialize response omitted serverInfo");

  const listed = await rpc(url, 2, "tools/list", {}, timeoutMs);
  const names = new Set((listed?.tools || []).map(tool => tool.name));
  for (const name of requiredTools) {
    if (!names.has(name)) throw new Error(`tools/list omitted ${name}`);
  }
  return Array.from(names).sort();
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const url = process.argv[2];
  if (!url) throw new Error("usage: node mcp-probe.mjs <streamable-http-url>");
  const tools = await probeMcp(url);
  console.log(JSON.stringify({ tools }));
}
