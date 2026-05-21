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
| `CONTEXT_KIT_DOCS_TTL` | `7d` | Docs re-fetch cadence |
| `CONTEXT_KIT_DOCS_SOURCES` | `config/sources.default.txt` | Space-separated source profile files |
| `CONTEXT_KIT_DOCS_MAX_GET_BYTES` | `75000` | Max bytes returned by docs retrieval |
| `CONTEXT_KIT_DOCS_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | SentenceTransformers embedding model |

## TTL Guidance

`7d` is the default because most reference docs do not need daily re-embedding.

Use shorter TTLs for fast-moving APIs:

```sh
CONTEXT_KIT_DOCS_TTL=72h bin/context-kit docs
```

Use longer TTLs for stable specs:

```sh
CONTEXT_KIT_DOCS_TTL=30d bin/context-kit docs
```

When freshness matters for one task, prefer a manual refresh through the docs
MCP tool instead of lowering the global TTL for every session.

## Source Profiles

The docs MCP accepts one or more source files:

```sh
CONTEXT_KIT_DOCS_SOURCES="config/sources.default.txt config/sources.js.txt"
```

Each source file is plain text. Blank lines and `#` comments are ignored.
