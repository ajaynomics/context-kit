import { spawn } from "node:child_process";

const command = process.argv[2];
const args = process.argv.slice(3);

if (!command) {
  throw new Error("usage: node scripts/smoke-web-search.mjs <command> [args...]");
}

const child = spawn(command, args, {
  cwd: new URL("..", import.meta.url).pathname,
  env: process.env,
  stdio: ["pipe", "pipe", "pipe"]
});

let nextId = 1;
const pending = new Map();
let stdoutBuffer = "";
let stderrBuffer = "";

function stopChild() {
  child.stdin.end();
  child.kill("SIGTERM");
  const killTimer = setTimeout(() => child.kill("SIGKILL"), 3000);
  return new Promise(resolve => {
    child.once("exit", () => {
      clearTimeout(killTimer);
      resolve();
    });
  });
}

const timeout = setTimeout(async () => {
  await stopChild();
  console.error(`MCP smoke timed out. stderr: ${stderrBuffer.slice(-2000)}`);
  process.exit(1);
}, 120000);

child.stderr.on("data", chunk => {
  stderrBuffer += chunk.toString();
});

child.stdout.on("data", chunk => {
  stdoutBuffer += chunk.toString();
  let newline;
  while ((newline = stdoutBuffer.indexOf("\n")) >= 0) {
    const line = stdoutBuffer.slice(0, newline).trim();
    stdoutBuffer = stdoutBuffer.slice(newline + 1);
    if (!line) continue;
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      continue;
    }
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(JSON.stringify(message.error)));
      else resolve(message.result);
    }
  }
});

function request(method, params = {}) {
  const id = nextId++;
  child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

function notify(method, params = {}) {
  child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method, params })}\n`);
}

function textFrom(result) {
  return (result.content || [])
    .filter(part => part.type === "text")
    .map(part => part.text)
    .join("\n");
}

async function callTool(name, args = {}) {
  return request("tools/call", { name, arguments: args });
}

try {
  await request("initialize", {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "context-kit-smoke", version: "0.0.0" }
  });
  notify("notifications/initialized");

  const listed = await request("tools/list");
  const toolNames = new Set((listed.tools || []).map(tool => tool.name));
  for (const name of ["search_web", "fetch_url"]) {
    if (!toolNames.has(name)) throw new Error(`missing tool: ${name}`);
  }

  const searxng = textFrom(await callTool("search_web", {
    q: "Model Context Protocol",
    limit: 2,
    provider: "searxng"
  }));
  if (!searxng.includes("Model")) throw new Error(`SearXNG smoke returned unexpected text: ${searxng.slice(0, 500)}`);

  const bing = textFrom(await callTool("search_web", {
    q: "Model Context Protocol",
    limit: 2,
    provider: "bing"
  }));
  if (!bing.includes("Model")) throw new Error(`Bing smoke returned unexpected text: ${bing.slice(0, 500)}`);

  const fetch = textFrom(await callTool("fetch_url", {
    url: "https://example.com/",
    format: "markdown",
    max_download_bytes: 52428800
  }));
  if (!fetch.includes("Example Domain")) throw new Error(`fetch smoke returned unexpected text: ${fetch.slice(0, 500)}`);

  const browserFetch = textFrom(await callTool("fetch_url", {
    url: "https://example.com/",
    format: "markdown",
    engine: "browser",
    max_download_bytes: 52428800
  }));
  if (!browserFetch.includes("Example Domain")) throw new Error(`browser fetch smoke returned unexpected text: ${browserFetch.slice(0, 500)}`);

  const localResult = await callTool("fetch_url", {
    url: "http://127.0.0.1:1/",
    max_download_bytes: 52428800
  });
  const localBlocked = Boolean(localResult.isError) && textFrom(localResult).includes("Blocked localhost/private URL");
  if (!localBlocked) throw new Error("localhost/private URL was not blocked as expected");

  clearTimeout(timeout);
  await stopChild();
  console.log(JSON.stringify({
    tools: Array.from(toolNames).sort(),
    searxng: "pass",
    bing: "pass",
    fetch_url: "pass",
    fetch_url_browser_engine_currently_http: "pass",
    localhost_guard: "pass"
  }, null, 2));
} catch (error) {
  clearTimeout(timeout);
  await stopChild();
  console.error(error.message);
  if (stderrBuffer) console.error(stderrBuffer.slice(-4000));
  process.exit(1);
}
