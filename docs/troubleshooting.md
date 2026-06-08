# Troubleshooting

## Run Doctor

```sh
bin/context-kit doctor
```

This checks Docker, Compose, images, the Docker network, SearXNG health, and
docs source configuration.

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

## Docs Indexing Is Slow

The first run downloads an embedding model and embeds every configured docs
section. Keep default sources small, and add profiles only when you need them.

Cloudflare and other large docs sets can take significantly longer than the
default source profile.

## Docs Tools Say Index Manager Not Initialized

If `docs_query` or `docs_refresh` returns `Index manager not initialized` while
`/status` still responds, the HTTP wrapper is up but `llms-txt-mcp` failed to
initialize its embedding model or Chroma database. Check the container logs:

```sh
docker logs context-kit-docs-mcp
```

A common cause is Docker creating the bind-mounted cache directories as `root`
before Context Kit created them as the host user. Look for errors like:

```text
Permission denied: '/models/models--BAAI--bge-small-en-v1.5'
unable to open database file
```

Fix ownership and restart:

```sh
DATA_DIR="${CONTEXT_KIT_DATA_DIR:-$HOME/.local/share/context-kit}"
sudo chown -R "$(id -u):$(id -g)" "$DATA_DIR/docs" "$DATA_DIR/models"
bin/context-kit restart
```

`bin/context-kit start` now pre-creates these directories and `doctor` reports
existing directories that are not writable by the current user. If an assistant
client reports `Session not found` after restarting `docs-mcp`, restart the
assistant so it opens a fresh Streamable HTTP MCP session.
