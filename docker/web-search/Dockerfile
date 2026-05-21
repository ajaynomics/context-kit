FROM node:22-bookworm-slim

ARG MCP_WEB_SEARCH_VERSION=1.3.0

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    chromium \
    fonts-liberation \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g "@zhafron/mcp-web-search@${MCP_WEB_SEARCH_VERSION}" \
  && npm cache clean --force

ENV CHROME_PATH=/usr/bin/chromium \
  DEFAULT_SEARCH_PROVIDER=searxng \
  HTTP_TIMEOUT=15000 \
  MAX_RESULTS=10 \
  SEARXNG_URL=http://searxng:8080

ENTRYPOINT ["mcp-web-search"]
