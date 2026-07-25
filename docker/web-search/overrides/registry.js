import { DuckDuckGoProvider } from "./duckduckgo.js";
import { BingProvider } from "./bing.js";
import { SearXNGProvider } from "./searxng.js";
import { BraveProvider } from "./brave.js";
import { DEFAULT_SEARCH_PROVIDER } from "../constants.js";
import { attemptProvider } from "./diagnostics.js";

const PROVIDERS = ["searxng", "brave", "duckduckgo", "bing"];
const PROVIDER_TIMEOUT_MS = Number(process.env.SEARCH_PROVIDER_TIMEOUT_MS || "15000");
const MAX_PROVIDER_ATTEMPTS = Math.max(1, Math.min(Number(process.env.MAX_PROVIDER_ATTEMPTS || "4"), 4));

export class ProviderRegistry {
  constructor(providers) {
    this.providers = providers || new Map([
      ["duckduckgo", new DuckDuckGoProvider()],
      ["bing", new BingProvider()],
      ["searxng", new SearXNGProvider()],
      ["brave", new BraveProvider()]
    ]);
  }

  get(name) {
    return this.providers.get(name);
  }

  async searchWithFallback(q, limit, lang, preferredProvider) {
    const defaultProvider = preferredProvider || DEFAULT_SEARCH_PROVIDER;
    const order = [defaultProvider, ...PROVIDERS.filter(name => name !== defaultProvider)].slice(0, MAX_PROVIDER_ATTEMPTS);
    const attempts = [];
    const started = performance.now();
    for (const providerName of order) {
      const provider = this.providers.get(providerName);
      if (!provider) continue;
      const attempt = await attemptProvider(provider, q, limit, lang, { timeoutMs: PROVIDER_TIMEOUT_MS });
      attempts.push(attempt.diagnostic);
      if (attempt.items.length) {
        return {
          items: attempt.items,
          providerUsed: providerName,
          fallbackUsed: providerName !== defaultProvider,
          triedProviders: attempts.map(item => item.provider),
          diagnostics: {
            attempts,
            elapsed_ms: Math.round(performance.now() - started),
            exhausted: false
          }
        };
      }
    }
    return {
      items: [],
      providerUsed: defaultProvider,
      fallbackUsed: attempts.length > 1,
      triedProviders: attempts.map(item => item.provider),
      diagnostics: {
        attempts,
        elapsed_ms: Math.round(performance.now() - started),
        exhausted: true
      }
    };
  }
}

export const providerRegistry = new ProviderRegistry();
export { DuckDuckGoProvider, BingProvider, SearXNGProvider, BraveProvider };
