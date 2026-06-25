import { requireToolSuccess, runSmoke, textFrom } from "./mcp-smoke-client.mjs";

const live = process.env.CONTEXT_KIT_LIVE_CHECKS === "1";

runSmoke({
  usage: "usage: node scripts/smoke-web-search.mjs <command> [args...]",
  tmpPrefix: "context-kit-web-search-smoke-",
  timeoutMs: 120000,
  clientInfo: { name: "context-kit-web-search-smoke", version: "0.0.0" },
  scenario: async client => {
    const toolNames = await client.requireTools(["search_web", "fetch_url"]);

    const localResult = await client.callTool("fetch_url", {
      url: "http://127.0.0.1:1/",
      max_download_bytes: 52428800
    });
    const localBlocked = Boolean(localResult.isError) && textFrom(localResult).includes("Blocked localhost/private URL");
    if (!localBlocked) throw new Error("localhost/private URL was not blocked as expected");

    const result = {
      tools: Array.from(toolNames).sort(),
      localhost_guard: "pass"
    };

    if (live) {
      const searxng = textFrom(requireToolSuccess("search_web/searxng", await client.callTool("search_web", {
        q: "Model Context Protocol",
        limit: 2,
        provider: "searxng"
      })));
      if (!searxng.includes("Model")) throw new Error(`SearXNG smoke returned unexpected text: ${searxng.slice(0, 500)}`);

      const bing = textFrom(requireToolSuccess("search_web/bing", await client.callTool("search_web", {
        q: "Model Context Protocol",
        limit: 2,
        provider: "bing"
      })));
      if (!bing.includes("Model")) throw new Error(`Bing smoke returned unexpected text: ${bing.slice(0, 500)}`);

      const fetch = textFrom(requireToolSuccess("fetch_url/http", await client.callTool("fetch_url", {
        url: "https://example.com/",
        format: "markdown",
        max_download_bytes: 52428800
      })));
      if (!fetch.includes("Example Domain")) throw new Error(`fetch smoke returned unexpected text: ${fetch.slice(0, 500)}`);

      const browserFetch = textFrom(requireToolSuccess("fetch_url/browser", await client.callTool("fetch_url", {
        url: "https://example.com/",
        format: "markdown",
        engine: "browser",
        max_download_bytes: 52428800
      })));
      if (!browserFetch.includes("Example Domain")) throw new Error(`browser fetch smoke returned unexpected text: ${browserFetch.slice(0, 500)}`);

      result.searxng = "pass";
      result.bing = "pass";
      result.fetch_url = "pass";
      result.fetch_url_browser_engine_currently_http = "pass";
    }

    return result;
  }
});
