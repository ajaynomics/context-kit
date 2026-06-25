import { PUPPETEER_TIMEOUT } from "../constants.js";
import { browserPool } from "../utils/browser-pool.js";
import { getAcceptLanguageHeader, getMarketFromLang } from "../utils/user-agent.js";
import { searchCache, createCacheKey } from "../utils/cache.js";

// Context Kit override for @zhafron/mcp-web-search 1.3.0.
// The upstream provider can read Bing before result cards render and return an
// empty fallback. Keep this as a direct provider replacement until upstream
// waits for cards and decodes current /ck/a redirects reliably.
const DEFAULT_BROWSER_SEARCH_USER_AGENT = process.env.BROWSER_SEARCH_USER_AGENT ||
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

function decodeBase64Url(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(normalized.length + ((4 - normalized.length % 4) % 4), "=");
  return Buffer.from(padded, "base64").toString("utf-8");
}

export class BingProvider {
  name = "bing";

  decodeBingRedirect(href) {
    try {
      const url = new URL(href, "https://www.bing.com/");
      if (url.hostname === "www.bing.com" && url.pathname === "/ck/a") {
        const encoded = url.searchParams.get("u");
        if (encoded) {
          const candidates = [encoded];
          if (/^[a-z][0-9]/i.test(encoded)) candidates.push(encoded.slice(2));
          for (const candidate of candidates) {
            try {
              const decoded = decodeBase64Url(candidate);
              if (/^https?:\/\//i.test(decoded)) return decoded;
            }
            catch { }
          }
        }
      }
      return url.toString();
    }
    catch {
      return href;
    }
  }

  async search(q, limit, lang) {
    const cacheKey = createCacheKey("bing", q, limit, lang);
    const cached = searchCache.get(cacheKey);
    if (cached)
      return cached;
    const market = getMarketFromLang(lang);
    const results = await browserPool.withBrowser(async (browser) => {
      const page = await browser.newPage();
      try {
        await page.setViewport({ width: 1365, height: 768 });
        await page.setUserAgent(DEFAULT_BROWSER_SEARCH_USER_AGENT);
        await page.setExtraHTTPHeaders(getAcceptLanguageHeader(lang));
        const url = new URL("https://www.bing.com/search");
        url.searchParams.set("q", q);
        url.searchParams.set("mkt", market);
        const response = await page.goto(url.toString(), {
          waitUntil: "domcontentloaded",
          timeout: PUPPETEER_TIMEOUT
        });
        if (response && response.status() >= 400) {
          throw new Error(`Bing HTTP ${response.status()}`);
        }
        await page.waitForSelector("li.b_algo h2 a[href], li.b_algo a[href]", { timeout: 10000 }).catch(() => undefined);
        const items = await page.evaluate(maxResults => {
          const parsed = [];
          for (const card of Array.from(document.querySelectorAll("li.b_algo"))) {
            const anchor = card.querySelector("h2 a[href]") || card.querySelector("a[href]");
            const title = anchor?.textContent?.trim() || "";
            const href = anchor?.getAttribute("href") || "";
            if (!title || !href)
              continue;
            const snippetElement = card.querySelector("div.b_caption p, div.b_snippet, p");
            const snippet = snippetElement?.textContent?.trim() || undefined;
            parsed.push({ title, url: href, snippet });
            if (parsed.length >= maxResults)
              break;
          }
          return parsed;
        }, limit);
        return items.flatMap(result => {
          try {
            const absolute = new URL(result.url, "https://www.bing.com/").toString();
            const decoded = this.decodeBingRedirect(absolute);
            new URL(decoded);
            return [{ ...result, url: decoded, source: "bing" }];
          }
          catch {
            return [];
          }
        });
      }
      finally {
        await page.close();
      }
    });
    searchCache.set(cacheKey, results);
    return results;
  }

  async isAvailable() {
    try {
      await browserPool.getBrowser();
      return true;
    }
    catch {
      return false;
    }
  }
}
