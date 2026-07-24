FROM node:22-bookworm-slim@sha256:813a7480f28fdadac1f7f5c824bcdad435b5bc1322a5968bbbdef8d058f9dff4

ARG MCP_WEB_SEARCH_VERSION=1.3.0
ARG MCP_WEB_SEARCH_MAX_BYTES=52428800
ARG MCP_PROXY_VERSION=0.12.0

COPY patch-mcp-web-search.mjs /tmp/patch-mcp-web-search.mjs
COPY overrides/bing.js /tmp/context-kit-bing-provider.js
COPY --chmod=0444 mcp-probe.mjs http-entrypoint.mjs /usr/local/lib/context-kit/

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

RUN python3 -m venv /opt/mcp-proxy \
  && /opt/mcp-proxy/bin/pip install --no-cache-dir "mcp-proxy==${MCP_PROXY_VERSION}" \
  && /opt/mcp-proxy/bin/mcp-proxy --version

RUN npm install -g "@zhafron/mcp-web-search@${MCP_WEB_SEARCH_VERSION}" \
  && cp /tmp/context-kit-bing-provider.js /usr/local/lib/node_modules/@zhafron/mcp-web-search/dist/src/providers/bing.js \
  && node /tmp/patch-mcp-web-search.mjs \
  && rm /tmp/patch-mcp-web-search.mjs /tmp/context-kit-bing-provider.js \
  && npm cache clean --force

ENV CHROME_PATH=/usr/bin/chromium \
  DEFAULT_SEARCH_PROVIDER=searxng \
  HOME=/tmp \
  HTTP_TIMEOUT=15000 \
  MAX_BYTES=${MCP_WEB_SEARCH_MAX_BYTES} \
  MAX_RESULTS=10 \
  PATH=/opt/mcp-proxy/bin:$PATH \
  SEARXNG_URL=http://searxng:8080 \
  XDG_CACHE_HOME=/tmp/.cache

USER node

EXPOSE 8000

ENTRYPOINT ["node", "/usr/local/lib/context-kit/http-entrypoint.mjs"]
