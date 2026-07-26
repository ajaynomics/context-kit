import http from "node:http";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

import { probeMcp } from "./mcp-probe.mjs";

const defaultUpstream = "http://127.0.0.1:8001";
export const mcpProxyArguments = Object.freeze([
  "--host", "127.0.0.1",
  "--port", "8001",
  "--stateless",
  "--pass-environment",
  "--",
  "mcp-web-search"
]);
const hopByHopHeaders = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade"
]);

export function hostAllowed(host) {
  if (!host) return false;
  const normalized = host.toLowerCase();
  return /^(localhost|127\.0\.0\.1)(:\d+)?$/.test(normalized)
    || /^\[::1\](:\d+)?$/.test(normalized)
    || normalized === "web-search-mcp:8000";
}

function copyRequestHeaders(headers, upstreamHost) {
  const copied = { ...headers, host: upstreamHost };
  for (const name of hopByHopHeaders) delete copied[name];
  delete copied.origin;
  return copied;
}

function copyResponseHeaders(headers) {
  const copied = {};
  for (const [name, value] of Object.entries(headers)) {
    if (!hopByHopHeaders.has(name) && !name.startsWith("access-control-")) copied[name] = value;
  }
  return copied;
}

export function createSecureMcpServer({ upstream = defaultUpstream, probe = probeMcp } = {}) {
  const target = new URL(upstream);
  return http.createServer(async (request, response) => {
    if (!hostAllowed(request.headers.host)) {
      response.writeHead(421, { "Content-Type": "text/plain" });
      response.end("Invalid Host header");
      return;
    }
    if (request.headers.origin !== undefined) {
      response.writeHead(403, { "Content-Type": "text/plain" });
      response.end("Invalid Origin header");
      return;
    }

    if (request.url === "/healthz") {
      try {
        await probe(`${upstream}/mcp`);
        response.writeHead(200, { "Content-Type": "text/plain" });
        response.end("ok");
      } catch (error) {
        response.writeHead(503, { "Content-Type": "text/plain" });
        response.end(`backend unavailable: ${error.message}`);
      }
      return;
    }

    if (!request.url?.startsWith("/")) {
      response.writeHead(400, { "Content-Type": "text/plain" });
      response.end("Invalid request target");
      return;
    }

    const upstreamRequest = http.request({
      hostname: target.hostname,
      port: target.port,
      method: request.method,
      path: request.url,
      headers: copyRequestHeaders(request.headers, target.host)
    }, upstreamResponse => {
      upstreamResponse.on("error", () => response.destroy());
      response.writeHead(
        upstreamResponse.statusCode || 502,
        copyResponseHeaders(upstreamResponse.headers)
      );
      upstreamResponse.pipe(response);
    });
    const abortUpstream = () => {
      if (!upstreamRequest.destroyed) upstreamRequest.destroy(new Error("downstream disconnected"));
    };
    request.once("aborted", abortUpstream);
    response.once("close", () => {
      if (!response.writableEnded) abortUpstream();
    });
    upstreamRequest.on("error", error => {
      if (response.destroyed) return;
      if (!response.headersSent) response.writeHead(502, { "Content-Type": "text/plain" });
      response.end(`backend unavailable: ${error.message}`);
    });
    request.pipe(upstreamRequest);
  });
}

export function superviseBackend({ probe, intervalMs = 10000, onFailure }) {
  let stopped = false;
  let timer;
  const check = async () => {
    if (stopped) return;
    try {
      await probe();
      timer = setTimeout(check, intervalMs);
    } catch (error) {
      stopped = true;
      onFailure(error);
    }
  };
  timer = setTimeout(check, intervalMs);
  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}

export async function terminateChild(child, { graceMs = 3000 } = {}) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const gracefulExit = once(child, "exit").then(() => true);
  child.kill("SIGTERM");
  const exited = await Promise.race([
    gracefulExit,
    delay(graceMs).then(() => false)
  ]);
  if (exited || child.exitCode !== null || child.signalCode !== null) return;

  const forcedExit = once(child, "exit");
  if (!child.kill("SIGKILL") && child.exitCode === null && child.signalCode === null) {
    throw new Error("failed to terminate mcp-proxy child");
  }
  await forcedExit;
}

async function waitForBackend(child, url) {
  let lastError;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`mcp-proxy exited during startup (${child.exitCode})`);
    try {
      await probeMcp(url, { timeoutMs: 1000 });
      return;
    } catch (error) {
      lastError = error;
      await delay(250);
    }
  }
  throw new Error(`web-search backend did not become ready: ${lastError?.message}`);
}

async function main() {
  const upstreamMcp = `${defaultUpstream}/mcp`;
  const child = spawn("mcp-proxy", mcpProxyArguments, { stdio: ["ignore", "inherit", "inherit"] });

  let server;
  let stopSupervisor = () => {};
  let shuttingDown = false;

  const shutdown = async (code, reason) => {
    if (shuttingDown) return;
    shuttingDown = true;
    if (reason) console.error(`web-search-mcp: ${reason}`);
    stopSupervisor();
    server?.close();
    server?.closeAllConnections();
    await terminateChild(child);
    process.exitCode = code;
  };

  child.once("exit", (code, signal) => {
    if (!shuttingDown) void shutdown(1, `mcp-proxy exited (code=${code}, signal=${signal})`);
  });
  process.once("SIGINT", () => void shutdown(0));
  process.once("SIGTERM", () => void shutdown(0));

  try {
    await waitForBackend(child, upstreamMcp);
    server = createSecureMcpServer();
    server.listen(8000, "0.0.0.0");
    await once(server, "listening");
    stopSupervisor = superviseBackend({
      probe: () => probeMcp(upstreamMcp),
      onFailure: error => void shutdown(1, `backend probe failed: ${error.message}`)
    });
  } catch (error) {
    await shutdown(1, error.message);
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) await main();
