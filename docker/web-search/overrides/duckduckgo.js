import { JSDOM } from "jsdom";
import { HTTP_TIMEOUT } from "../constants.js";
import { fetchWithTimeout } from "../utils/http.js";
import { getRandomUserAgent, getAcceptLanguageHeader } from "../utils/user-agent.js";
import { searchCache, createCacheKey } from "../utils/cache.js";

export class DuckDuckGoProvider {
  name = "duckduckgo";

  decodeDuckDuckGoRedirect(href) {
    try {
      const url = new URL(href, "https://duckduckgo.com/");
      if (url.hostname === "duckduckgo.com" && url.pathname.startsWith("/l/")) {
        const target = url.searchParams.get("uddg");
        if (target) return decodeURIComponent(target);
      }
      return url.toString();
    } catch {
      return href;
    }
  }

  async search(q, limit, lang, signal) {
    const cacheKey = createCacheKey("ddg", q, limit, lang);
    const cached = searchCache.get(cacheKey);
    if (cached) return cached;
    const url = new URL("https://html.duckduckgo.com/html/");
    url.searchParams.set("q", q);
    const headers = { "User-Agent": getRandomUserAgent(), ...getAcceptLanguageHeader(lang) };
    const response = await fetchWithTimeout(url, { headers, signal }, HTTP_TIMEOUT);
    if (!response.ok) throw new Error(`DuckDuckGo HTML ${response.status}`);
    const dom = new JSDOM(await response.text(), { url: `https://duckduckgo.com/?q=${encodeURIComponent(q)}` });
    const anchors = Array.from(dom.window.document.querySelectorAll("a.result__a"));
    const snippets = Array.from(dom.window.document.querySelectorAll(".result__snippet"));
    const items = [];
    for (let index = 0; index < anchors.length && items.length < limit; index += 1) {
      const title = (anchors[index].textContent || "").trim();
      const href = this.decodeDuckDuckGoRedirect(anchors[index].getAttribute("href") || "");
      if (!title || !href) continue;
      try {
        items.push({
          title,
          url: new URL(href).toString(),
          snippet: (snippets[index]?.textContent || "").trim() || undefined,
          source: "duckduckgo"
        });
      } catch {}
    }
    searchCache.set(cacheKey, items);
    return items;
  }

  async isAvailable() {
    return true;
  }
}
