import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";

import {
  createSecureMcpServer,
  mcpProxyArguments,
  superviseBackend
} from "../docker/web-search/http-entrypoint.mjs";
import { probeMcp } from "../docker/web-search/mcp-probe.mjs";

let backendAlive = true;
assert(mcpProxyArguments.includes("--stateless"));
const backend = http.createServer(async (request, response) => {
  if (request.url === "/status") {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end('{"server_instances":{"default":"configured"}}');
    return;
  }
  if (request.method !== "POST" || request.url !== "/mcp") {
    response.writeHead(404).end();
    return;
  }

  let body = "";
  for await (const chunk of request) body += chunk;
  const message = JSON.parse(body);
  if (message.method === "initialize") {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({
      jsonrpc: "2.0",
      id: message.id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "mock-web-search", version: "1" }
      }
    }));
    return;
  }
  if (message.method === "tools/list" && backendAlive) {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({
      jsonrpc: "2.0",
      id: message.id,
      result: { tools: [{ name: "search_web" }, { name: "fetch_url" }] }
    }));
    return;
  }
  response.writeHead(500, { "Content-Type": "text/plain" });
  response.end("backend dead");
});
backend.listen(0, "127.0.0.1");
await once(backend, "listening");
const backendPort = backend.address().port;
const upstream = `http://127.0.0.1:${backendPort}`;

const front = createSecureMcpServer({ upstream });
front.listen(0, "127.0.0.1");
await once(front, "listening");
const frontPort = front.address().port;

function rawRequest({ host, origin }) {
  return new Promise((resolve, reject) => {
    const headers = {
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
      Host: host
    };
    if (origin !== undefined) headers.Origin = origin;
    const request = http.request({
      hostname: "127.0.0.1",
      port: frontPort,
      path: "/mcp",
      method: "POST",
      headers
    }, response => {
      response.resume();
      response.once("end", () => resolve(response.statusCode));
    });
    request.once("error", reject);
    request.end('{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}');
  });
}

const tools = await probeMcp(`http://127.0.0.1:${frontPort}/mcp`);
assert.deepEqual(tools, ["fetch_url", "search_web"]);
assert.equal(await rawRequest({ host: "attacker.example" }), 421);
assert.equal(await rawRequest({ host: `127.0.0.1:${frontPort}`, origin: "https://attacker.example" }), 403);
assert.equal(await rawRequest({ host: `127.0.0.1:${frontPort}`, origin: `http://127.0.0.1:${frontPort}` }), 403);

backendAlive = false;
assert.equal((await fetch(`${upstream}/status`)).status, 200);
assert.equal((await fetch(`http://127.0.0.1:${frontPort}/healthz`)).status, 503);

await new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error("backend supervisor did not detect death")), 1000);
  const stop = superviseBackend({
    probe: () => probeMcp(`${upstream}/mcp`, { timeoutMs: 100 }),
    intervalMs: 10,
    onFailure: () => {
      clearTimeout(timeout);
      stop();
      resolve();
    }
  });
});

front.close();
front.closeAllConnections();
backend.close();
backend.closeAllConnections();
console.log("pass web-search HTTP security and supervision tests");
