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
| `CONTEXT_KIT_COMPOSE_PROJECT` | `context-kit` | Docker Compose project and network prefix |
| `CONTEXT_KIT_SEARXNG_PORT` | `8099` | Localhost SearXNG port |
| `CONTEXT_KIT_WEB_SEARCH_MAX_BYTES` | `52428800` | Max bytes `context-web-search` accepts and downloads per fetch |
| `CONTEXT_KIT_WEB_SEARCH_PROVIDER` | `searxng` | Default `search_web` provider; fallback order depends on this provider |
| `CONTEXT_KIT_WEB_SEARCH_HTTP_TIMEOUT` | `15000` | HTTP timeout in milliseconds for search providers |
| `CONTEXT_KIT_WEB_SEARCH_MAX_RESULTS` | `10` | Default search result count when clients omit `limit` |
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
| `CONTEXT_KIT_DOCS_PREINDEX` | `0` | Set to `1` to re-embed every source on container start |
| `CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR` | `${CONTEXT_KIT_DATA_DIR}/local-sources` | Machine-local llms.txt tree mounted read-only into docs-mcp |
| `CONTEXT_KIT_DOCS_LOCAL_SOURCES_PORT` | `8769` | Loopback port inside docs-mcp for serving local source files |

## TTL Guidance

`24h` is the default. Most reference docs do not need re-embedding more often,
and the shared service does not re-fetch sources until the TTL elapses.

Use shorter TTLs for fast-moving APIs:

```sh
CONTEXT_KIT_DOCS_TTL=6h bin/context-kit restart
```

Use longer TTLs for stable specs:

```sh
CONTEXT_KIT_DOCS_TTL=30d bin/context-kit restart
```

The docs-mcp container reads `CONTEXT_KIT_DOCS_TTL` at startup, so changes
require `bin/context-kit restart`. When freshness matters for one task, prefer
calling the `docs_refresh` MCP tool instead of lowering the global TTL.

## Browser CORS

`context-docs` disables browser CORS by default. CLI assistants and server-side
HTTP clients do not need CORS. If a browser-based local client must call the MCP
endpoint directly, allow only the exact local origin(s) it uses:

```sh
CONTEXT_KIT_DOCS_ALLOW_ORIGIN="http://127.0.0.1:3000 http://localhost:3000" \
  bin/context-kit restart
```

Avoid `*`; the docs MCP is a local unauthenticated endpoint.

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
