# Context Kit

Local context tools for Claude Code and OpenCode.

Local web search. Local docs. Repo packing. No API keys required.

## What You Get

Context Kit gives coding agents three local tools:

| Tool | Purpose |
|---|---|
| `context-web-search` | Current web search through local SearXNG plus URL fetch/extract |
| `context-docs` | Semantic search over curated `llms.txt` documentation |
| `context-repomix` | Pack repositories into AI-friendly context |

The first public release deliberately keeps the surface area small: web search,
docs search, and repository packing.

## Quick Start

```sh
git clone https://gitea.krishnan.ca/ajaynomics/context-kit.git
cd context-kit
cp .env.example .env
export PATH="$PWD/bin:$PATH"
bin/context-kit start
bin/context-kit doctor
```

Then connect your assistant.

For Claude Code:

```sh
bin/context-kit install claude
```

Copy the printed JSON into your project's `.mcp.json`, or use the equivalent
`claude mcp add` commands if you prefer managing servers through the Claude CLI.
The default snippet uses `context-kit` on `PATH`, which is the right shape for
shared project config. For a private user-only config, you can print absolute
paths with `bin/context-kit install claude --absolute`.

For OpenCode:

```sh
bin/context-kit install opencode
```

Merge the printed `mcp` block into your `opencode.json`, then restart OpenCode.
The default snippet uses `context-kit` on `PATH`. Use
`bin/context-kit install opencode --absolute` only for private, machine-local
config that will not be committed.

## How It Runs

- SearXNG binds to `127.0.0.1:8099` only.
- `context-web-search` and `context-repomix` run as local stdio MCP commands.
- `context-docs` runs as a local HTTP MCP service. `bin/context-kit docs` is a
  stdio fallback for clients that cannot use HTTP MCP.
- `context-docs` browser CORS is disabled by default; set exact local origins
  only when a browser-based client needs direct access.
- Docs and model caches live in `$HOME/.local/share/context-kit`.
- Docs refresh TTL defaults to `24h`.
- Repomix mounts only the current project read-only.
- No code-editing MCP server is enabled by default.

## Public Repo vs Local Runtime State

This repository is the public, portable Context Kit distribution. It should only
contain generic defaults, Docker/service code, install snippets, and optional
public docs source profiles.

Machine-specific configuration stays out of git:

- `.env` is ignored. Use it for local ports, data paths, and private source
  profile paths.
- `CONTEXT_KIT_DATA_DIR` stores runtime state: docs indexes, model caches, the
  generated `docs-sources.txt`, and any local source tree you choose to keep
  there.
- Private docs source profiles can live anywhere outside the repo and can be
  referenced from `.env` with an absolute path.
- Private `llms.txt` menus belong under `CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR`, not
  under `config/`.

The public default is intentionally small: `config/sources.default.txt`. If a
machine adds extra local menus, they affect only that machine's running
`context-docs` service.

## Docs Sources

The default docs index is intentionally small:

- Claude Code docs
- OpenAI API docs and reference
- OpenRouter docs
- Model Context Protocol docs

Optional profiles live in `config/`:

- `sources.ruby-ai.txt`
- `sources.js.txt`
- `sources.cloudflare.txt`

Example:

```sh
CONTEXT_KIT_DOCS_SOURCES="config/sources.default.txt config/sources.js.txt" \
  bin/context-kit restart
```

Source changes are loaded by `start`/`restart`; `bin/context-kit docs` is only a
stdio bridge to the already-running docs service.

Large vendor feeds are opt-in because they can expand to thousands of sections
and take a while to embed.

## Commands

```sh
bin/context-kit start
bin/context-kit stop
bin/context-kit build
bin/context-kit status
bin/context-kit doctor
bin/context-kit install claude
bin/context-kit install opencode
bin/context-kit redaction-check
```

MCP entrypoints:

```sh
bin/context-kit web-search
bin/context-kit docs
bin/context-kit repomix
```

After pulling Context Kit updates, rebuild local images and restart services:

```sh
bin/context-kit build
bin/context-kit restart
```

## Security Model

Context Kit is local-first, but MCP tools still extend what your agent can do.

- Treat fetched web pages as untrusted input.
- Do not expose SearXNG publicly without changing the secret and reviewing its
  configuration.
- Keep docs profiles curated. More sources means more background indexing and
  more untrusted text in your retrieval corpus.
- Be cautious when adding code-editing MCP servers. Context Kit's default MCP
  servers either read remote content or mount the current project read-only.

See `docs/security.md` for details.

## Requirements

- Docker with Compose v2
- Bash
- `curl` for health checks

No hosted API keys are required for the default stack.

## License

MIT
