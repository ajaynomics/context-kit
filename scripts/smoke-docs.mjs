import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const command = process.argv[2];
const args = process.argv.slice(3);

if (!command) {
  throw new Error("usage: node scripts/smoke-docs.mjs <command> [args...]");
}

const tmpDir = mkdtempSync(join(tmpdir(), "context-kit-docs-smoke-"));
const cidFile = join(tmpDir, "container.cid");

const child = spawn(command, args, {
  cwd: new URL("..", import.meta.url).pathname,
  env: { ...process.env, CONTEXT_KIT_DOCKER_CIDFILE: cidFile },
  stdio: ["pipe", "pipe", "pipe"]
});

let nextId = 1;
const pending = new Map();
let stdoutBuffer = "";
let stderrBuffer = "";
let childExited = false;

child.once("exit", (code, signal) => {
  childExited = true;
  if (pending.size > 0) {
    const error = new Error(`MCP child exited before responding (code=${code}, signal=${signal}). stderr: ${stderrBuffer.slice(-2000)}`);
    for (const { reject } of pending.values()) reject(error);
    pending.clear();
  }
});

function stopChild() {
  return new Promise(resolve => {
    if (childExited) {
      stopContainer();
      rmSync(tmpDir, { recursive: true, force: true });
      resolve();
      return;
    }

    child.stdin.end();
    const stopTimer = setTimeout(() => {
      stopContainer();
    }, 1000);
    const termTimer = setTimeout(() => {
      if (!childExited) child.kill("SIGTERM");
    }, 3000);
    const killTimer = setTimeout(() => {
      if (!childExited) child.kill("SIGKILL");
    }, 6000);

    child.once("exit", () => {
      stopContainer();
      clearTimeout(stopTimer);
      clearTimeout(termTimer);
      clearTimeout(killTimer);
      rmSync(tmpDir, { recursive: true, force: true });
      resolve();
    });
  });
}

function stopContainer() {
  if (!existsSync(cidFile)) return;
  const containerId = readFileSync(cidFile, "utf8").trim();
  if (!containerId) return;
  spawnSync("docker", ["stop", containerId], { stdio: "ignore" });
}

const timeout = setTimeout(async () => {
  await stopChild();
  console.error(`Docs MCP smoke timed out. stderr: ${stderrBuffer.slice(-2000)}`);
  process.exit(1);
}, 300000);

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
  if (childExited) {
    return Promise.reject(new Error(`MCP child already exited. stderr: ${stderrBuffer.slice(-2000)}`));
  }
  const id = nextId++;
  child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

function notify(method, params = {}) {
  child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method, params })}\n`);
}

async function callTool(name, args = {}) {
  return request("tools/call", { name, arguments: args });
}

try {
  await request("initialize", {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "context-kit-docs-smoke", version: "0.0.0" }
  });
  notify("notifications/initialized");

  const listed = await request("tools/list");
  const toolNames = new Set((listed.tools || []).map(tool => tool.name));
  for (const name of ["docs_query", "docs_sources"]) {
    if (!toolNames.has(name)) throw new Error(`missing tool: ${name}`);
  }

  const sources = await callTool("docs_sources");
  const sourcesText = JSON.stringify(sources);
  if (sources.isError) {
    throw new Error(`docs_sources returned an error: ${sourcesText.slice(0, 500)}`);
  }

  const query = await callTool("docs_query", {
    query: "Model Context Protocol documentation",
    limit: 3,
    auto_retrieve: true,
    auto_retrieve_threshold: 0.1,
    auto_retrieve_limit: 1,
    max_bytes: 12000
  });
  const queryText = JSON.stringify(query);
  if (!queryText.includes("search_results") && !queryText.includes("Model Context Protocol")) {
    throw new Error(`docs_query returned unexpected payload: ${queryText.slice(0, 500)}`);
  }

  clearTimeout(timeout);
  await stopChild();
  console.log(JSON.stringify({
    tools: Array.from(toolNames).sort(),
    docs_sources: "pass",
    docs_query: "pass"
  }, null, 2));
} catch (error) {
  clearTimeout(timeout);
  await stopChild();
  console.error(error.message);
  if (stderrBuffer) console.error(stderrBuffer.slice(-4000));
  process.exit(1);
}
