import { HTTP_TIMEOUT, SEARXNG_URL } from "../constants.js";
import { fetchWithTimeout } from "../utils/http.js";
import { getRandomUserAgent, getAcceptLanguageHeader } from "../utils/user-agent.js";
import { searchCache, createCacheKey } from "../utils/cache.js";

export class SearXNGProvider {
  name = "searxng";

  constructor(instanceUrl) {
    this.instanceUrl = instanceUrl || SEARXNG_URL;
  }

  async search(q, limit, lang, signal) {
    const cacheKey = createCacheKey("searxng", q, limit, lang);
    const cached = searchCache.get(cacheKey);
    if (cached) return cached;
    const params = new URLSearchParams({ q, format: "json", language: lang, safesearch: "0" });
    const response = await fetchWithTimeout(`${this.instanceUrl}/search?${params}`, {
      headers: { "User-Agent": getRandomUserAgent(), ...getAcceptLanguageHeader(lang) },
      signal
    }, HTTP_TIMEOUT);
    if (!response.ok) {
      if (response.status === 403) throw new Error("SearXNG JSON API disabled");
      throw new Error(`SearXNG error: ${response.status}`);
    }
    const data = await response.json();
    const items = (data.results || []).slice(0, limit).map(result => ({
      title: result.title || "",
      url: result.url || "",
      snippet: result.content || undefined,
      source: "searxng"
    }));
    searchCache.set(cacheKey, items);
    return items;
  }

  async isAvailable() {
    try {
      const response = await fetchWithTimeout(`${this.instanceUrl}/search?q=test&format=json`, {
        headers: { Accept: "application/json", "User-Agent": getRandomUserAgent() }
      }, 5000);
      return response.ok;
    } catch {
      return false;
    }
  }
}
