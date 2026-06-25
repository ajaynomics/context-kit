import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export function textFrom(result) {
  return (result.content || [])
    .filter(part => part.type === "text")
    .map(part => part.text)
    .join("\n");
}

export function requireToolSuccess(name, result) {
  if (result?.isError) {
    const payload = textFrom(result) || JSON.stringify(result);
    throw new Error(`${name} returned an error: ${payload.slice(0, 500)}`);
  }
  return result;
}

export async function runSmoke({ usage, tmpPrefix, timeoutMs, clientInfo, scenario }) {
  const command = process.argv[2];
  const args = process.argv.slice(3);

  if (!command) {
    throw new Error(usage);
  }

  const client = new McpSmokeClient({ command, args, tmpPrefix });
  const timeout = setTimeout(async () => {
    await client.stop();
    console.error(`MCP smoke timed out. stderr: ${client.stderrTail(2000)}`);
    process.exit(1);
  }, timeoutMs);

  try {
    await client.initialize(clientInfo);
    const result = await scenario(client);
    clearTimeout(timeout);
    await client.stop();
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    clearTimeout(timeout);
    await client.stop();
    console.error(error.message);
    const stderr = client.stderrTail(4000);
    if (stderr) console.error(stderr);
    process.exit(1);
  }
}

class McpSmokeClient {
  constructor({ command, args, tmpPrefix }) {
    this.tmpDir = mkdtempSync(join(tmpdir(), tmpPrefix));
    this.cidFile = join(this.tmpDir, "container.cid");
    this.nextId = 1;
    this.pending = new Map();
    this.stdoutBuffer = "";
    this.stderrBuffer = "";
    this.exited = false;

    this.child = spawn(command, args, {
      cwd: new URL("..", import.meta.url).pathname,
      env: { ...process.env, CONTEXT_KIT_DOCKER_CIDFILE: this.cidFile },
      stdio: ["pipe", "pipe", "pipe"]
    });

    this.child.once("exit", (code, signal) => {
      this.exited = true;
      if (this.pending.size > 0) {
        const error = new Error(`MCP child exited before responding (code=${code}, signal=${signal}). stderr: ${this.stderrTail(2000)}`);
        for (const { reject } of this.pending.values()) reject(error);
        this.pending.clear();
      }
    });

    this.child.stderr.on("data", chunk => {
      this.stderrBuffer += chunk.toString();
    });

    this.child.stdout.on("data", chunk => this.handleStdout(chunk));
  }

  stderrTail(length) {
    return this.stderrBuffer.slice(-length);
  }

  handleStdout(chunk) {
    this.stdoutBuffer += chunk.toString();
    let newline;
    while ((newline = this.stdoutBuffer.indexOf("\n")) >= 0) {
      const line = this.stdoutBuffer.slice(0, newline).trim();
      this.stdoutBuffer = this.stdoutBuffer.slice(newline + 1);
      if (!line) continue;
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        continue;
      }
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result);
      }
    }
  }

  request(method, params = {}) {
    if (this.exited) {
      return Promise.reject(new Error(`MCP child already exited. stderr: ${this.stderrTail(2000)}`));
    }
    const id = this.nextId++;
    this.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }

  notify(method, params = {}) {
    this.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method, params })}\n`);
  }

  async initialize(clientInfo) {
    await this.request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo
    });
    this.notify("notifications/initialized");
  }

  async tools() {
    const listed = await this.request("tools/list");
    return new Set((listed.tools || []).map(tool => tool.name));
  }

  async requireTools(names) {
    const toolNames = await this.tools();
    for (const name of names) {
      if (!toolNames.has(name)) throw new Error(`missing tool: ${name}`);
    }
    return toolNames;
  }

  callTool(name, args = {}) {
    return this.request("tools/call", { name, arguments: args });
  }

  stopContainer() {
    if (!existsSync(this.cidFile)) return;
    const containerId = readFileSync(this.cidFile, "utf8").trim();
    if (!containerId) return;
    spawnSync("docker", ["stop", containerId], { stdio: "ignore" });
  }

  stop() {
    return new Promise(resolve => {
      if (this.exited) {
        this.stopContainer();
        rmSync(this.tmpDir, { recursive: true, force: true });
        resolve();
        return;
      }

      let stopTimer;
      let termTimer;
      let killTimer;
      this.child.once("exit", () => {
        this.stopContainer();
        clearTimeout(stopTimer);
        clearTimeout(termTimer);
        clearTimeout(killTimer);
        rmSync(this.tmpDir, { recursive: true, force: true });
        resolve();
      });

      stopTimer = setTimeout(() => this.stopContainer(), 1000);
      termTimer = setTimeout(() => {
        if (!this.exited) this.child.kill("SIGTERM");
      }, 3000);
      killTimer = setTimeout(() => {
        if (!this.exited) this.child.kill("SIGKILL");
      }, 6000);

      this.child.stdin.end();
    });
  }
}
