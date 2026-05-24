#!/bin/sh
# context-kit docs-mcp entrypoint.
#
# Bridges llms-txt-mcp (stdio-only) to Streamable HTTP via mcp-proxy so that
# multiple clients share a single long-lived indexer instead of each spawning
# their own container (and racing on the same Chroma store).
#
# Sources are read from $DOCS_MCP_SOURCES_FILE (one URL per line; `#` comments
# and blank lines are allowed). Everything else is configured via env vars
# with sensible defaults so this image works standalone too.

set -eu

sources_file="${DOCS_MCP_SOURCES_FILE:-/etc/context-kit/docs-sources.txt}"

if [ ! -r "$sources_file" ]; then
  echo "docs-mcp: sources file not readable: $sources_file" >&2
  echo "docs-mcp: set DOCS_MCP_SOURCES_FILE or mount one at that path." >&2
  exit 64
fi

# Strip comments and blank lines, then collapse whitespace into a flat list.
sources=$(grep -vE '^[[:space:]]*(#|$)' "$sources_file" | tr -s '[:space:]' '\n' | grep -v '^$' || true)

if [ -z "$sources" ]; then
  echo "docs-mcp: no sources found in $sources_file after stripping comments/blanks" >&2
  exit 64
fi

# By default llms-txt-mcp 0.2.0 re-embeds every source on launch (the actual
# default is a background preindex, --no-preindex only disables the foreground
# variant). On a long-lived container that just wastes ~5 min of CPU per
# restart, so we disable BOTH and let the caller use `docs_refresh` on demand.
# Set DOCS_MCP_PREINDEX=1 to restore the eager behavior.
preindex_flag="--no-preindex --no-background-preindex"
if [ "${DOCS_MCP_PREINDEX:-0}" = "1" ]; then
  preindex_flag=""
fi

# shellcheck disable=SC2086  # intentional word-splitting on $sources / $preindex_flag
exec mcp-proxy \
  --host "${DOCS_MCP_HTTP_HOST:-0.0.0.0}" \
  --port "${DOCS_MCP_HTTP_PORT:-8000}" \
  --pass-environment \
  --allow-origin "${DOCS_MCP_ALLOW_ORIGIN:-*}" \
  -- \
  llms-txt-mcp \
    --store-path /data \
    --ttl "${DOCS_MCP_TTL:-24h}" \
    --max-get-bytes "${DOCS_MCP_MAX_GET_BYTES:-75000}" \
    --embed-model "${DOCS_MCP_EMBED_MODEL:-BAAI/bge-small-en-v1.5}" \
    $preindex_flag \
    $sources
