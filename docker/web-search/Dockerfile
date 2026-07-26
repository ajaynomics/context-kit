FROM node:22-bookworm-slim@sha256:813a7480f28fdadac1f7f5c824bcdad435b5bc1322a5968bbbdef8d058f9dff4

ARG MCP_WEB_SEARCH_VERSION=1.3.0
ARG MCP_WEB_SEARCH_MAX_BYTES=52428800
ARG MCP_PROXY_VERSION=0.12.0
ARG MCP_PYTHON_SDK_VERSION=1.28.1

# Chromium intentionally tracks Debian security updates inside the pinned base
# image family; Bing's browser path is more likely to break with stale Chromium
# than with patched OS packages.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    chromium \
    fonts-liberation \
    python3-venv \
  && rm -rf /var/lib/apt/lists/*

COPY patch-mcp-proxy.py /tmp/patch-mcp-proxy.py

RUN python3 -m venv /opt/mcp-proxy \
  && /opt/mcp-proxy/bin/pip install --no-cache-dir \
    "mcp-proxy==${MCP_PROXY_VERSION}" \
    "mcp==${MCP_PYTHON_SDK_VERSION}" \
  && /opt/mcp-proxy/bin/python /tmp/patch-mcp-proxy.py \
  && /opt/mcp-proxy/bin/mcp-proxy --version

COPY patch-mcp-web-search.mjs /tmp/patch-mcp-web-search.mjs
COPY overrides/bing.js /tmp/context-kit-bing-provider.js
COPY overrides/brave.js overrides/duckduckgo.js overrides/searxng.js overrides/registry.js overrides/diagnostics.mjs /tmp/context-kit-providers/
COPY overrides/browser-fetch.js overrides/bounds.mjs /tmp/context-kit-fetch/
COPY --chmod=0444 mcp-probe.mjs http-entrypoint.mjs /usr/local/lib/context-kit/

RUN npm install -g "@zhafron/mcp-web-search@${MCP_WEB_SEARCH_VERSION}" \
  && cp /tmp/context-kit-bing-provider.js /usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/providers/bing.js \
  && cp /tmp/context-kit-providers/brave.js /usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/providers/brave.js \
  && cp /tmp/context-kit-providers/duckduckgo.js /usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/providers/duckduckgo.js \
  && cp /tmp/context-kit-providers/searxng.js /usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/providers/searxng.js \
  && cp /tmp/context-kit-providers/registry.js /usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/providers/registry.js \
  && cp /tmp/context-kit-providers/diagnostics.mjs /usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/providers/diagnostics.js \
  && cp /tmp/context-kit-fetch/browser-fetch.js /usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/fetch/browser.js \
  && cp /tmp/context-kit-fetch/bounds.mjs /usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/fetch/bounds.js \
  && node /tmp/patch-mcp-web-search.mjs \
  && rm -rf /tmp/patch-mcp-proxy.py /tmp/patch-mcp-web-search.mjs /tmp/context-kit-bing-provider.js /tmp/context-kit-providers /tmp/context-kit-fetch \
  && npm cache clean --force

RUN chmod -R a+rX /usr/local/lib/context-kit \
      /usr/local/lib/node_modules/@zhafron/mcp-web-search

ENV CHROME_PATH=/usr/bin/chromium \
  DEFAULT_SEARCH_PROVIDER=searxng \
  HOME=/tmp \
  HTTP_TIMEOUT=15000 \
  MAX_BYTES=${MCP_WEB_SEARCH_MAX_BYTES} \
  MAX_RESULTS=10 \
  MAX_PROVIDER_ATTEMPTS=4 \
  SEARCH_PROVIDER_TIMEOUT_MS=15000 \
  PATH=/opt/mcp-proxy/bin:$PATH \
  SEARXNG_URL=http://searxng:8080 \
  XDG_CACHE_HOME=/tmp/.cache

USER node

EXPOSE 8000

ENTRYPOINT ["node", "/usr/local/lib/context-kit/http-entrypoint.mjs"]
