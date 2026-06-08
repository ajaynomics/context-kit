# Configuration

Configuration is via environment variables or a `.env` file in the repository
root. Start from `.env.example`.

Explicit environment variables win over `.env` values. The `.env` parser accepts
simple `KEY=VALUE` lines for `CONTEXT_KIT_*` variables only; it does not execute
shell code.

## Core Variables

| Variable | Default | Purpose |
|---|---|---|
| `CONTEXT_KIT_DATA_DIR` | `$HOME/.local/share/context-kit` | Persistent docs indexes and model cache |
| `CONTEXT_KIT_COMPOSE_PROJECT` | `context-kit` | Docker Compose project and network prefix |
| `CONTEXT_KIT_SEARXNG_PORT` | `8099` | Localhost SearXNG port |
| `CONTEXT_KIT_DOCS_PORT` | `8776` | Localhost port for the long-lived docs-mcp HTTP service |
| `CONTEXT_KIT_DOCS_HTTP_URL` | `http://127.0.0.1:${CONTEXT_KIT_DOCS_PORT}/mcp` | URL emitted into HTTP MCP install snippets |
| `CONTEXT_KIT_DOCS_ALLOW_ORIGIN` | unset | Optional exact browser CORS origin(s) for docs-mcp, separated by spaces |
| `CONTEXT_KIT_DOCS_TTL` | `24h` | Docs re-fetch cadence |
| `CONTEXT_KIT_DOCS_SOURCES` | `config/sources.default.txt` | Space-separated source profile files |
| `CONTEXT_KIT_DOCS_MAX_GET_BYTES` | `75000` | Max bytes returned by docs retrieval |
| `CONTEXT_KIT_DOCS_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | SentenceTransformers embedding model |
| `CONTEXT_KIT_DOCS_PREINDEX` | `0` | Set to `1` to re-embed every source on container start |

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

The docs MCP accepts one or more source files:

```sh
CONTEXT_KIT_DOCS_SOURCES="config/sources.default.txt config/sources.js.txt"
```

Each source file is plain text. Blank lines and `#` comments are ignored.
