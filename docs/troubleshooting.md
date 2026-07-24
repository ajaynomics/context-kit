# Troubleshooting

## Run Doctor

```sh
bin/context-kit doctor
```

This checks Docker, Compose, images, the Docker network, SearXNG health, a real
web-search MCP initialize/tools-list exchange, docs HTTP readiness, and docs
source configuration.

For release-grade MCP protocol checks, run:

```sh
scripts/release-check
```

Live provider checks are opt-in because search engines, remote docs, and model
downloads can fail independently of this repo:

```sh
CONTEXT_KIT_LIVE_CHECKS=1 scripts/release-check
```

## SearXNG Is Not Responding

Start it:

```sh
bin/context-kit start
```

Then check:

```sh
curl 'http://127.0.0.1:8099/search?q=test&format=json'
```

If you changed `CONTEXT_KIT_SEARXNG_PORT`, use that port instead.

## MCP Image Missing

Build default images:

```sh
bin/context-kit build
```

## Repeated Per-Project Containers

Current OpenCode and Claude snippets connect web search and docs directly to the
shared HTTP services. If every project still starts a web-search container,
regenerate the snippet, update the assistant configuration, and restart the
assistant:

```sh
bin/context-kit install opencode
bin/context-kit install claude
```

For the upgrade from `origin/main`, build and start once. `start` creates only
the missing web-search service and refuses to recreate existing services:

```sh
bin/context-kit build
bin/context-kit start
```

Context Kit never performs a global Docker prune. Inspect labeled resources and
their owners explicitly:

```sh
docker ps -a --filter label=dev.context-kit=true \
  --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Label "dev.context-kit.lifecycle"}}\t{{.Label "dev.context-kit.owner"}}\t{{.Label "com.docker.compose.service"}}'
```

Containers from the old per-call web-search launcher have an empty Compose
service and no lifecycle/owner labels. After all old assistant processes are
stopped, remove only the exact legacy container IDs you verified; do not use a
name-pattern or global prune.

Lifecycle commands for one Compose project use a canonical, uid-owned lock and
reject cross-user control. Failed startup removes only newly-created service
containers, restores existing container states by ID, and never removes the
network or cache volume. `start` uses Compose `--no-recreate`, leaving an
existing container unchanged when its image or environment differs from the
current Compose model; it never silently replaces that container. Inspect the
shared services without deleting them:

```sh
bin/context-kit status
docker compose -p "${CONTEXT_KIT_COMPOSE_PROJECT:-context-kit}" -f compose.yml logs web-search-mcp docs-mcp searxng
```

Use the protocol-level doctor check. `/healthz` also performs initialize and
tools/list rather than trusting the proxy's static `/status` metadata:

```sh
bin/context-kit doctor
curl http://127.0.0.1:8777/healthz
```

`bin/context-kit status` lists legacy labeled containers that have neither a
Compose service nor lifecycle label. This is diagnostic only; Context Kit never
auto-removes them. Stop their old assistant owners before removing individually
verified container IDs.

## Fetch URL Says Max Download Bytes Is Too Big

If `fetch_url` fails before making a network request with an MCP validation error
like `Number must be less than or equal to 26214400`, rebuild the web-search MCP
image:

```sh
bin/context-kit build
```

Context Kit patches the upstream `mcp-web-search` schema so the accepted
`max_download_bytes` value matches `CONTEXT_KIT_WEB_SEARCH_MAX_BYTES`, which
defaults to `52428800`.

## Search Fallback and Chromium

`search_web` defaults to SearXNG. If SearXNG fails or returns no results, the
upstream fallback order is DuckDuckGo, then Bing. Bing uses Chromium through
Puppeteer, so `bin/context-kit doctor` checks that the configured Chromium path
exists inside the web-search image.

Context Kit carries a source-controlled Bing provider override in
`docker/web-search/overrides/bing.js` because the upstream 1.3.0 provider can
race result rendering and return no items even when Chromium sees Bing result
cards. The override waits for result cards and decodes current Bing redirect
URLs before handing results back to the upstream fallback registry.

`fetch_url` is different: in upstream `mcp-web-search` 1.3.0, `engine=browser` is
accepted but reserved for future support. It does not currently invoke Chromium;
URL fetching uses the HTTP extractor path.

## Docs Indexing Is Slow

The first `docs_query` or `docs_refresh` downloads an embedding model and
embeds the requested docs sections lazily. Keep default sources small, and add
profiles only when you need them.

Cloudflare and other large docs sets can take significantly longer than the
default source profile. Set `CONTEXT_KIT_DOCS_PREINDEX=1` only if you want
startup to eagerly embed every configured source.

## Docs Tools Say Index Manager Not Initialized

If `docs_query` or `docs_refresh` returns `Index manager not initialized` while
`/status` still responds, the HTTP wrapper is up but `llms-txt-mcp` failed to
initialize its embedding model or Chroma database. Check the container logs:

```sh
docker compose -p "${CONTEXT_KIT_COMPOSE_PROJECT:-context-kit}" -f compose.yml logs docs-mcp
```

A common cause is Docker creating the bind-mounted cache directories as `root`
before Context Kit created them as the host user. Look for errors like:

```text
Permission denied: '/models/models--BAAI--bge-small-en-v1.5'
unable to open database file
```

Fix ownership and restart:

```sh
DATA_DIR="${CONTEXT_KIT_DATA_DIR:-${HOME:?Set HOME or CONTEXT_KIT_DATA_DIR}/.local/share/context-kit}"
sudo chown -R "$(id -u):$(id -g)" "$DATA_DIR/docs" "$DATA_DIR/models"
bin/context-kit restart
```

`bin/context-kit start` now pre-creates these directories and `doctor` reports
existing directories that are not writable by the current user. If an assistant
client reports `Session not found` after restarting `docs-mcp`, restart the
assistant so it opens a fresh Streamable HTTP MCP session.
