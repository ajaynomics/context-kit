const DEFAULT_TIMEOUT_MS = 15_000;
const MAX_ERROR_LENGTH = 240;

export function classifyProviderError(error) {
  const message = error instanceof Error ? error.message : String(error);
  const lower = message.toLowerCase();
  let category = "provider_error";
  if (lower.includes("timed out") || lower.includes("timeout")) category = "timeout";
  else if (lower.includes("429") || lower.includes("rate limit")) category = "rate_limited";
  else if (lower.includes("captcha") || lower.includes("challenge")) category = "blocked";
  else if (lower.includes("403") || lower.includes("401") || lower.includes("denied")) category = "forbidden";
  else if (lower.includes("network") || lower.includes("fetch") || lower.includes("socket")) category = "network";
  return { category, message: message.replace(/\s+/g, " ").slice(0, MAX_ERROR_LENGTH) };
}

export async function attemptProvider(provider, query, limit, lang, options = {}) {
  const timeoutMs = Math.max(10, Math.min(options.timeoutMs || DEFAULT_TIMEOUT_MS, 60_000));
  const now = options.now || (() => performance.now());
  const started = now();
  if (provider.configured === false) {
    return {
      items: [],
      diagnostic: { provider: provider.name, status: "unavailable", duration_ms: 0, result_count: 0 }
    };
  }
  let timer;
  const controller = new AbortController();
  try {
    const items = await Promise.race([
      provider.search(query, limit, lang, controller.signal),
      new Promise((_, reject) => {
        timer = setTimeout(() => {
          controller.abort(new Error(`provider timed out after ${timeoutMs}ms`));
          reject(new Error(`provider timed out after ${timeoutMs}ms`));
        }, timeoutMs);
      })
    ]);
    const bounded = Array.isArray(items) ? items.slice(0, limit) : [];
    return {
      items: bounded,
      diagnostic: {
        provider: provider.name,
        status: bounded.length ? "success" : "empty",
        duration_ms: Math.max(0, Math.round(now() - started)),
        result_count: bounded.length
      }
    };
  } catch (error) {
    return {
      items: [],
      diagnostic: {
        provider: provider.name,
        status: "error",
        duration_ms: Math.max(0, Math.round(now() - started)),
        result_count: 0,
        error: classifyProviderError(error)
      }
    };
  } finally {
    controller.abort();
    clearTimeout(timer);
  }
}
