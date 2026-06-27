import { requireToolSuccess, runSmoke } from "./mcp-smoke-client.mjs";

const live = process.env.CONTEXT_KIT_LIVE_CHECKS === "1";
const localSourceSmokeUrl = process.env.CONTEXT_KIT_LOCAL_SOURCE_SMOKE_URL;

runSmoke({
  usage: "usage: node scripts/smoke-docs.mjs <command> [args...]",
  tmpPrefix: "context-kit-docs-smoke-",
  timeoutMs: 300000,
  clientInfo: { name: "context-kit-docs-smoke", version: "0.0.0" },
  scenario: async client => {
    const toolNames = await client.requireTools(["docs_query", "docs_sources"]);

    const sources = requireToolSuccess("docs_sources", await client.callTool("docs_sources"));
    if (!Array.isArray(sources?.structuredContent?.result)) {
      const sourcesText = JSON.stringify(sources);
      throw new Error(`docs_sources returned unexpected payload: ${sourcesText.slice(0, 500)}`);
    }

    const result = {
      tools: Array.from(toolNames).sort(),
      docs_sources: "pass"
    };

    if (localSourceSmokeUrl) {
      requireToolSuccess("docs_refresh/local_source_first", await client.callTool("docs_refresh", {
        source: localSourceSmokeUrl
      }));
      requireToolSuccess("docs_refresh/local_source_second", await client.callTool("docs_refresh", {
        source: localSourceSmokeUrl
      }));
      result.local_source_refresh = "pass";
    }

    if (live) {
      const query = requireToolSuccess("docs_query", await client.callTool("docs_query", {
        query: "Model Context Protocol documentation",
        limit: 3,
        auto_retrieve: true,
        auto_retrieve_threshold: 0.1,
        auto_retrieve_limit: 1,
        max_bytes: 12000
      }));
      const queryText = JSON.stringify(query);
      if (!queryText.includes("search_results") && !queryText.includes("Model Context Protocol")) {
        throw new Error(`docs_query returned unexpected payload: ${queryText.slice(0, 500)}`);
      }
      result.docs_query = "pass";
    }

    return result;
  }
});
