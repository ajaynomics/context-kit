import { HTTP_TIMEOUT } from "../constants.js";
import { searchCache, createCacheKey } from "../utils/cache.js";

export class BraveProvider {
  name = "brave";
  configured = Boolean(process.env.BRAVE_SEARCH_API_KEY);

  async search(q, limit, lang, signal) {
    if (!this.configured) return [];
    const cacheKey = createCacheKey("brave", q, limit, lang);
    const cached = searchCache.get(cacheKey);
    if (cached) return cached;
    const url = new URL("https://api.search.brave.com/res/v1/web/search");
    url.searchParams.set("q", q);
    url.searchParams.set("count", String(Math.min(limit, 20)));
    url.searchParams.set("search_lang", lang.split(/[-_]/)[0] || "en");
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        "X-Subscription-Token": process.env.BRAVE_SEARCH_API_KEY
      },
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(HTTP_TIMEOUT)]) : AbortSignal.timeout(HTTP_TIMEOUT)
    });
    if (!response.ok) throw new Error(`Brave HTTP ${response.status}`);
    const data = await response.json();
    const items = (data.web?.results || []).slice(0, limit).flatMap(result => {
      if (!result.title || !result.url) return [];
      return [{
        title: result.title,
        url: result.url,
        snippet: result.description || undefined,
        source: "brave"
      }];
    });
    searchCache.set(cacheKey, items);
    return items;
  }

  async isAvailable() {
    return this.configured;
  }
}
