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
