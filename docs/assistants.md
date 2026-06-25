# Assistant Setup

Context Kit supports assistants that can run local stdio MCP servers, HTTP MCP
servers, or both. The default transport split is simple:

- `context-web-search`: local stdio command.
- `context-docs`: local HTTP MCP service.
- `context-repomix`: local stdio command.

`bin/context-kit docs` is a stdio fallback for clients that cannot use HTTP MCP.
The included snippets cover Claude Code and OpenCode.

## Claude Code

Print a project `.mcp.json` snippet:

```sh
bin/context-kit install claude
```

The default snippet uses `context-kit` on `PATH`, which is appropriate for
committed project config. For private user-only config, you can print absolute
paths with:

```sh
bin/context-kit install claude --absolute
```

Claude Code also supports adding stdio servers through its CLI. Use absolute
paths if `context-kit` is not on your `PATH`.

After configuration, open Claude Code and run:

```text
/mcp
```

You should see:

- `context-web-search`
- `context-docs`
- `context-repomix`

## OpenCode

Print an `opencode.json` MCP snippet:

```sh
bin/context-kit install opencode
```

Merge the printed `mcp` block into your OpenCode config and restart OpenCode.
OpenCode reads config at startup.

Use `bin/context-kit install opencode --absolute` only for private machine-local
config that will not be committed.

## Suggested Agent Instructions

Use the snippets in `snippets/CLAUDE.md` and `snippets/AGENTS.md` as a starting
point. They remind agents to use docs search before guessing API details and to
treat fetched web pages as untrusted input.
