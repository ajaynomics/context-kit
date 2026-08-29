# Configuration

Configuration is via environment variables or a `.env` file in the repository
root. Start from `.env.example`.

Explicit environment variables win over `.env` values. The `.env` parser accepts
simple `KEY=VALUE` lines for `CONTEXT_KIT_*` variables only; it does not execute
shell code.

## Public Files vs Local State

Context Kit is meant to be a public repo plus private local runtime state.

Tracked public files:

- `config/sources.default.txt`: small default docs index.
- `config/sources.*.txt`: optional public source profiles.
- `snippets/`: portable assistant config snippets that use `context-kit` on
  `PATH`.
- `compose.yml`, `docker/`, `bin/`, and `scripts/`: generic runtime and release
  logic.

Ignored or external local files:

- `.env`: local overrides; never commit it.
- `CONTEXT_KIT_DATA_DIR`: docs indexes, model caches, generated
  `docs-sources.txt`, and local source trees.
- Private source profile files referenced by absolute path from `.env`.
- Private `llms.txt` menus under `CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR`.

Do not put personal project menus, private repo names, or local filesystem paths
in `config/`. Put them in a private source profile outside the repo, then add
that profile to `.env`:

```sh
CONTEXT_KIT_DOCS_SOURCES="config/sources.default.txt /path/to/private-sources.txt"
CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR=/path/to/local-sources
```

Entries in the private profile should still be URLs, not filesystem paths. For a
local menu stored at `/path/to/local-sources/my-project/llms.txt`, reference it
as:

```text
http://127.0.0.1:8769/my-project/llms.txt
```

That loopback URL is inside the `docs-mcp` container. It is not exposed on the
host.

## User-Facing Variables

Only the variables below are part of the public configuration surface. Other
`CONTEXT_KIT_*` variables used by scripts are release/test hooks and may change.

| Variable | Default | Purpose |
|---|---|---|
| `CONTEXT_KIT_DATA_DIR` | `$HOME/.local/share/context-kit` | Persistent docs indexes and model cache |
| `CONTEXT_KIT_COMPOSE_PROJECT` | `context-kit` | Shared-service ownership boundary and Compose name prefix |
| `CONTEXT_KIT_SEARXNG_PORT` | `8099` | Localhost SearXNG port. Engines are Bing and Google; DuckDuckGo is disabled |
| `CONTEXT_KIT_WEB_SEARCH_PORT` | `8777` | Localhost port for the long-lived web-search HTTP service |
| `CONTEXT_KIT_WEB_SEARCH_HTTP_URL` | `http://127.0.0.1:${CONTEXT_KIT_WEB_SEARCH_PORT}/mcp` | URL emitted into HTTP MCP install snippets |
| `CONTEXT_KIT_WEB_SEARCH_MAX_BYTES` | `52428800` | Max bytes `context-web-search` accepts and downloads per fetch |
| `CONTEXT_KIT_WEB_SEARCH_PROVIDER` | `searxng` | Default `search_web` provider; fallback order depends on this provider |
| `CONTEXT_KIT_WEB_SEARCH_HTTP_TIMEOUT` | `15000` | HTTP timeout in milliseconds for search providers |
| `CONTEXT_KIT_WEB_SEARCH_MAX_RESULTS` | `10` | Default search result count when clients omit `limit` |
| `CONTEXT_KIT_WEB_SEARCH_MAX_PROVIDER_ATTEMPTS` | `4` | Maximum providers attempted for one search |
| `CONTEXT_KIT_WEB_SEARCH_PROVIDER_TIMEOUT` | `15000` | Per-provider diagnostic timeout in milliseconds |
| `CONTEXT_KIT_BRAVE_SEARCH_API_KEY` | unset | Optional Brave Search API fallback credential |
| `CONTEXT_KIT_WEB_SEARCH_CHROME_PATH` | `/usr/bin/chromium` | Chromium path inside the web-search image for Bing fallback |
| `CONTEXT_KIT_WEB_SEARCH_BROWSER_USER_AGENT` | bundled Chrome/Linux UA | User agent for the Chromium-backed Bing fallback |
| `CONTEXT_KIT_WEB_SEARCH_MCP_COMPAT_MODE` | unset | Set to `legacy` for MCP clients with weak tool-schema parsers |
| `CONTEXT_KIT_DOCS_PORT` | `8776` | Localhost port for the long-lived docs-mcp HTTP service |
| `CONTEXT_KIT_DOCS_HTTP_URL` | `http://127.0.0.1:${CONTEXT_KIT_DOCS_PORT}/mcp` | URL emitted into HTTP MCP install snippets |
| `CONTEXT_KIT_DOCS_ALLOW_ORIGIN` | unset | Optional exact browser CORS origin(s) for docs-mcp, separated by spaces |
| `CONTEXT_KIT_DOCS_TTL` | `24h` | Docs re-fetch cadence |
| `CONTEXT_KIT_DOCS_SOURCES` | `config/sources.default.txt` | Space-separated source profile files |
| `CONTEXT_KIT_DOCS_MAX_GET_BYTES` | `75000` | Max bytes returned by docs retrieval |
| `CONTEXT_KIT_DOCS_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | SentenceTransformers embedding model |
| `CONTEXT_KIT_DOCS_PREINDEX` | `0` | Set to `1` to refresh stale/missing sources in the background on startup |
| `CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR` | `${CONTEXT_KIT_DATA_DIR}/local-sources` | Machine-local llms.txt tree mounted read-only into docs-mcp |
| `CONTEXT_KIT_DOCS_LOCAL_SOURCES_PORT` | `8769` | Loopback port inside docs-mcp for serving local source files |

## Docker Ownership

One Compose project owns the shared `searxng`, `web-search-mcp`, and `docs-mcp`
services. Compose derives stable container and network names from
`CONTEXT_KIT_COMPOSE_PROJECT`; the default network is `context-kit_default`.
Compose's existing labels remain the ownership markers for SearXNG, docs, the
network, and `searxng-cache`. Their definitions are unchanged from
`origin/main`, avoiding a resource-recreation prompt. The new web-search service
also records `dev.context-kit.uid`.

`start`, `stop`, and `restart` use one canonical
`/tmp/context-kit-PROJECT.lock` directory, which must be a non-symlink directory
owned by the current uid with mode `0700`. Existing docs and web-search
containers must have the same uid; cross-user lifecycle control is rejected.

`start` passes `--no-recreate` to Compose. On failure it removes only service
containers that did not exist before the attempt, restores prior running/stopped
states by exact container ID, and leaves the deterministic network and cache
volume intact for reuse. `restart` operates on the same container IDs and uses
the same state restoration. Neither command replaces an existing container.
`stop` stops containers without removing them or their network.

The stdio bridge commands and Repomix create uniquely named client containers
with `dev.context-kit.lifecycle=client` and an invocation-specific owner label.
Their cleanup verifies that owner label before removing the exact container ID.

Web search runs stateless MCP sessions. Its front end accepts only loopback Host
values or the internal `web-search-mcp:8000` service name and returns 403 for any
request carrying Origin. It probes initialize and tools/list periodically; a
dead stdio backend terminates the container so Docker can restart it.

`restart` restarts existing container IDs, so it reloads bind-mounted docs source
files but does not apply rebuilt images or changed container environment. There
is intentionally no automatic replacement path while the old container cannot
be restored transactionally.

## TTL Guidance

`24h` is the default. Most reference docs do not need re-embedding more often,
and the shared service does not re-fetch sources until the TTL elapses.

Set a shorter TTL in `.env` for fast-moving APIs:

```dotenv
CONTEXT_KIT_DOCS_TTL=6h
```

Set a longer TTL for stable specs:

```dotenv
CONTEXT_KIT_DOCS_TTL=30d
```

The docs-mcp container environment is fixed when Compose creates it. A safe
same-ID `restart` does not apply a changed TTL; it takes effect only when a new
container is explicitly provisioned. When freshness matters for one task,
prefer `docs_refresh` instead of replacing the shared container.

Use `bin/context-kit docs-rebuild [SOURCE_URL ...]` after parser/model changes or
to force an atomic rebuild. Existing searchable generations remain available if
a source fetch, parse, or embedding step fails.

## Browser CORS

`context-docs` disables browser CORS by default. CLI assistants and server-side
HTTP clients do not need CORS. If a browser-based local client must call the MCP
endpoint directly, allow only the exact local origin(s) it uses:

```dotenv
CONTEXT_KIT_DOCS_ALLOW_ORIGIN="http://127.0.0.1:3000 http://localhost:3000"
```

Avoid `*`; the docs MCP is a local unauthenticated endpoint. Like other
container-environment changes, this takes effect only on explicit provisioning
of a new docs container, not a same-ID `restart`.

## Source Profiles

The docs MCP accepts one or more source profile files:

```sh
CONTEXT_KIT_DOCS_SOURCES="config/sources.default.txt config/sources.js.txt"
```

Source changes are loaded when the docs service starts. Run `bin/context-kit
restart` after changing `CONTEXT_KIT_DOCS_SOURCES`; `bin/context-kit docs` only
bridges stdio clients to the already-running service.

`CONTEXT_KIT_DOCS_SOURCES` may include absolute paths to private machine-local
profile files. Each profile file is plain text; blank lines and `#` comments are
ignored. Entries inside profile files must be URLs ending in `/llms.txt` or
`/llms-full.txt`.

For local llms.txt files, place content under
`CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR` and reference it as
`http://127.0.0.1:8769/path/inside/local-sources/llms.txt` or another URL that
ends in `/llms.txt` or `/llms-full.txt`; that loopback URL is inside the docs-mcp
container, not exposed on the host.

Run `bin/context-kit docs-snapshot [--only DIRECTORY]` to materialize linked
local menus. Each successful directory gets `llms-full.txt` and
`llms-full.provenance.json`; cache validators live under
`${CONTEXT_KIT_DATA_DIR}/snapshot-cache`. `--offline` rebuilds only from that
cache. During `start`/`restart`, a local `/llms.txt` URL is automatically changed
to its sibling `/llms-full.txt` when that file exists.
