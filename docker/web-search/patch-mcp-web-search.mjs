import fs from "node:fs";

// Context Kit patch for @zhafron/mcp-web-search 1.3.0.
// Upstream hard-codes the fetch_url schema limit to 25 MiB even though the
// runtime extractor already uses MAX_BYTES. Keep this narrow and fail the build
// if upstream changes the compiled source shape.
const serverPath = "/usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/server.js";
let source = fs.readFileSync(serverPath, "utf8");

const replacements = [
  [
    'import { MAX_RESULTS } from "./constants.js";',
    'import { MAX_BYTES, MAX_RESULTS } from "./constants.js";'
  ],
  [
    "max_download_bytes: z.number().int().min(1).max(26214400).optional()",
    "max_download_bytes: z.number().int().min(1).max(MAX_BYTES).optional()"
  ],
  [
    'provider: z.enum(["duckduckgo", "bing", "searxng"]).optional()',
    'provider: z.enum(["duckduckgo", "bing", "searxng", "brave"]).optional()'
  ],
  [
    "Search the web using multiple providers (DuckDuckGo, Bing, SearXNG). Automatically falls back to other providers if the default fails. No API keys required for DuckDuckGo and SearXNG.",
    "Search the web with bounded provider fallback and per-attempt diagnostics. SearXNG is local; Brave is available when BRAVE_SEARCH_API_KEY is configured."
  ],
  [
    '}, async ({ q, limit = DEFAULT_LIMIT, lang = "en", provider }) => {',
    '}, async ({ q, limit = DEFAULT_LIMIT, lang = "en", provider }, { signal }) => {'
  ],
  [
    "providerRegistry.searchWithFallback(q, Math.min(Math.max(1, limit), 50), lang, provider)",
    "providerRegistry.searchWithFallback(q, Math.min(Math.max(1, limit), 50), lang, provider, signal)"
  ],
  [
    '}, async ({ url, format, max_length, start_index, engine, include_links, include_media, include_metadata, include_comments, comment_limit, comment_sort, max_depth, timeout_ms, fresh, download, download_dir, download_ttl_seconds, max_download_bytes }) => {',
    '}, async ({ url, format, max_length, start_index, engine, include_links, include_media, include_metadata, include_comments, comment_limit, comment_sort, max_depth, timeout_ms, fresh, download, download_dir, download_ttl_seconds, max_download_bytes }, { signal }) => {'
  ],
  [
    "        max_download_bytes\n    });",
    "        max_download_bytes,\n        signal\n    });"
  ]
];

for (const [before, after] of replacements) {
  if (!source.includes(before)) {
    throw new Error(`mcp-web-search patch target not found: ${before}`);
  }
  source = source.replace(before, after);
}

fs.writeFileSync(serverPath, source);

const httpPath = "/usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/fetch/http.js";
let httpSource = fs.readFileSync(httpPath, "utf8");
const privateTransport = "async function fetchViaVettedAddress(url, timeoutMs)";
if (!httpSource.includes(privateTransport)) throw new Error(`mcp-web-search patch target not found: ${privateTransport}`);
httpSource = httpSource.replace(privateTransport, "export async function fetchViaVettedAddress(url, timeoutMs, signal)");
const requestTimeout = "            timeout: timeoutMs\n        }, response => {";
if (!httpSource.includes(requestTimeout)) throw new Error(`mcp-web-search patch target not found: ${requestTimeout}`);
httpSource = httpSource.replace(requestTimeout, "            timeout: timeoutMs,\n            signal\n        }, response => {");
const transportCall = "response = await transport(currentUrl, timeoutMs);";
if (!httpSource.includes(transportCall)) throw new Error(`mcp-web-search patch target not found: ${transportCall}`);
httpSource = httpSource.replace(transportCall, "response = await transport(currentUrl, timeoutMs, options?.signal);");
fs.writeFileSync(httpPath, httpSource);

const utilityHttpPath = "/usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/utils/http.js";
let utilityHttpSource = fs.readFileSync(utilityHttpPath, "utf8");
const uncombinedSignal = 'return await fetch(input, { ...init, signal: controller.signal });';
const combinedSignal = 'const signal = init.signal ? AbortSignal.any([init.signal, controller.signal]) : controller.signal;\n        return await fetch(input, { ...init, signal });';
if (!utilityHttpSource.includes(uncombinedSignal)) throw new Error(`mcp-web-search patch target not found: ${uncombinedSignal}`);
utilityHttpSource = utilityHttpSource.replace(uncombinedSignal, combinedSignal);
fs.writeFileSync(utilityHttpPath, utilityHttpSource);

const extractPath = "/usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/extract.js";
let extractSource = fs.readFileSync(extractPath, "utf8");
const extractReplacements = [
  [
    'import { assertSafeUrl } from "./fetch/security.js";',
    'import { assertSafeUrl } from "./fetch/security.js";\nimport { fetchBrowserResource } from "./fetch/browser.js";\nimport { boundFetchCollections } from "./fetch/bounds.js";'
  ],
  [
    "fetchCache.set(cacheKey, siteResult);\n        return siteResult;",
    "const boundedSiteResult = boundFetchCollections(siteResult);\n        options?.signal?.throwIfAborted();\n        fetchCache.set(cacheKey, boundedSiteResult);\n        return boundedSiteResult;"
  ],
  [
    "const resource = await fetchResource(parsedUrl, options?.timeout_ms, transport, options);",
    'const resource = options?.engine === "browser"\n        ? await fetchBrowserResource(parsedUrl, options?.timeout_ms, options?.signal)\n        : await fetchResource(parsedUrl, options?.timeout_ms, transport, options);\n    options?.signal?.throwIfAborted();'
  ],
  [
    "fetchCache.set(cacheKey, result);\n    return result;",
    "result = boundFetchCollections(result);\n    options?.signal?.throwIfAborted();\n    fetchCache.set(cacheKey, result);\n    return result;"
  ]
];
const fetchStart = "export async function fetchAndExtract(url, options, transport) {\n    const parsedUrl = new URL(url);";
if (!extractSource.includes(fetchStart)) throw new Error(`mcp-web-search extract patch target not found: ${fetchStart}`);
extractSource = extractSource.replace(fetchStart, "export async function fetchAndExtract(url, options, transport) {\n    options?.signal?.throwIfAborted();\n    const parsedUrl = new URL(url);");
for (const [before, after] of extractReplacements) {
  if (!extractSource.includes(before)) throw new Error(`mcp-web-search extract patch target not found: ${before}`);
  extractSource = extractSource.replace(before, after);
}
fs.writeFileSync(extractPath, extractSource);
