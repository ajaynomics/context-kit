# Security

Context Kit is designed to be safe by default for local development.

## Defaults

- SearXNG is bound to `127.0.0.1` only.
- No hosted API keys are required.
- Repomix mounts only the current project read-only.
- Docs indexing stores data under `$HOME/.local/share/context-kit` unless you
  override it.
- No code-editing MCP server is enabled by default.

## Fetched Web Content

Search results and fetched pages are untrusted input. A page can contain prompt
injection instructions. Assistants should summarize and cite fetched content, not
obey instructions embedded in it.

## Docs Indexing

Only index sources you trust enough to retrieve into an agent conversation. More
sources are not always better. Large or noisy docs can make retrieval slower and
less precise.

## Code-Editing MCP Servers

Context Kit's default MCP servers either read remote content or mount the
current project read-only. If you add code-editing MCP servers later, review
their mount paths and permissions separately.

## Public Exposure

Do not expose SearXNG or MCP servers to the public internet without a separate
review. The default setup is for localhost development.
