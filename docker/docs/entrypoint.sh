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
local_sources_dir="${DOCS_MCP_LOCAL_SOURCES_DIR:-/etc/context-kit/local-sources}"
local_sources_port="${DOCS_MCP_LOCAL_SOURCES_PORT:-8769}"

if [ ! -f "$sources_file" ]; then
  echo "docs-mcp: sources file missing: $sources_file" >&2
  echo "docs-mcp: run bin/context-kit start to generate it, or mount a file at that path." >&2
  exit 64
fi

if [ ! -r "$sources_file" ]; then
  echo "docs-mcp: sources file not readable: $sources_file" >&2
  echo "docs-mcp: set DOCS_MCP_SOURCES_FILE or mount one at that path." >&2
  exit 64
fi

# Strip inline comments and blank lines, then collapse whitespace into a flat list.
sources=$(sed 's/#.*//' "$sources_file" | tr -s '[:space:]' '\n' | grep -v '^$' || true)

if [ -z "$sources" ]; then
  echo "docs-mcp: no sources found in $sources_file after stripping comments/blanks" >&2
  exit 64
fi

for source_url in $sources; do
  case "$source_url" in
    */llms.txt|*/llms-full.txt) ;;
    *)
      echo "docs-mcp: source URL must end with /llms.txt or /llms-full.txt: $source_url" >&2
      exit 64
      ;;
  esac
done

if [ -d "$local_sources_dir" ]; then
  python - "$local_sources_port" "$local_sources_dir" >/tmp/context-kit-local-sources.log 2>&1 <<'PY' &
import functools
import http.server
import sys


class LocalSourceHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        # llms-txt-mcp 0.2.0 treats 304 responses from local sources as fetch
        # failures, so serve machine-local docs as plain 200 responses.
        for header in ("If-Modified-Since", "If-None-Match"):
            if header in self.headers:
                del self.headers[header]
        return super().send_head()


port = int(sys.argv[1])
directory = sys.argv[2]
handler = functools.partial(LocalSourceHandler, directory=directory)
with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
    server.serve_forever()
PY
  local_sources_pid="$!"
  if ! python - "$local_sources_port" <<'PY'
import sys
import time
import urllib.request

port = sys.argv[1]
last_error = None
for _ in range(20):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.5) as response:
            if response.status < 500:
                raise SystemExit(0)
    except Exception as error:
        last_error = error
        time.sleep(0.1)
raise SystemExit(f"local source server did not become ready: {last_error}")
PY
  then
    kill "$local_sources_pid" 2>/dev/null || true
    echo "docs-mcp: local source server failed on 127.0.0.1:$local_sources_port" >&2
    exit 65
  fi
fi

# By default llms-txt-mcp 0.2.0 re-embeds every source on launch (the actual
# default is a background preindex, --no-preindex only disables the foreground
# variant). On a long-lived container that wastes CPU per restart, so we disable
# BOTH. Missing/stale sources still refresh on first docs_query/docs_refresh.
# Set DOCS_MCP_PREINDEX=1 to restore eager startup indexing.
preindex_flag="--no-preindex --no-background-preindex"
if [ "${DOCS_MCP_PREINDEX:-0}" = "1" ]; then
  preindex_flag=""
fi

allow_origin_args=""
if [ -n "${DOCS_MCP_ALLOW_ORIGIN:-}" ]; then
  allow_origin_args="--allow-origin ${DOCS_MCP_ALLOW_ORIGIN}"
fi

# shellcheck disable=SC2086  # intentional word-splitting on $sources / $preindex_flag / $allow_origin_args
exec mcp-proxy \
  --host "${DOCS_MCP_HTTP_HOST:-0.0.0.0}" \
  --port "${DOCS_MCP_HTTP_PORT:-8000}" \
  --pass-environment \
  $allow_origin_args \
  -- \
  llms-txt-mcp \
    --store-path /data \
    --ttl "${DOCS_MCP_TTL:-24h}" \
    --max-get-bytes "${DOCS_MCP_MAX_GET_BYTES:-75000}" \
    --embed-model "${DOCS_MCP_EMBED_MODEL:-BAAI/bge-small-en-v1.5}" \
    $preindex_flag \
    $sources
