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
  options.signal?.throwIfAborted();
  if (provider.configured === false) {
    return {
      items: [],
      diagnostic: { provider: provider.name, status: "unavailable", duration_ms: 0, result_count: 0 }
    };
  }
  const controller = new AbortController();
  const signal = options.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal;
  const timer = setTimeout(() => {
    controller.abort(new Error(`provider timed out after ${timeoutMs}ms`));
  }, timeoutMs);
  try {
    const items = await provider.search(query, limit, lang, signal);
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
    options.signal?.throwIfAborted();
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
    clearTimeout(timer);
  }
}
