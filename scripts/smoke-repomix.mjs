import { requireToolSuccess, runSmoke, textFrom } from "./mcp-smoke-client.mjs";

runSmoke({
  usage: "usage: node scripts/smoke-repomix.mjs <command> [args...]",
  tmpPrefix: "context-kit-repomix-smoke-",
  timeoutMs: 120000,
  clientInfo: { name: "context-kit-repomix-smoke", version: "0.0.0" },
  scenario: async client => {
    const toolNames = await client.requireTools(["pack_codebase"]);

    const pack = requireToolSuccess("pack_codebase", await client.callTool("pack_codebase", {
      directory: process.cwd(),
      compress: true,
      includePatterns: "README.md,snippets/opencode.json",
      ignorePatterns: "",
      topFilesLength: 2,
      style: "xml"
    }));

    const packText = textFrom(pack) || JSON.stringify(pack);
    if (!packText.includes("Successfully packed codebase") && !packText.includes("outputId")) {
      throw new Error(`pack_codebase returned unexpected payload: ${packText.slice(0, 500)}`);
    }

    return {
      tools: Array.from(toolNames).sort(),
      pack_codebase: "pass"
    };
  }
});
