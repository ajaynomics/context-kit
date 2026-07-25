from __future__ import annotations

import asyncio
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .embedder import SentenceTransformerEmbedder
from .fetcher import SourceFetcher
from .parser import parse_llms_text
from .refresh import RefreshCoordinator
from .search import HybridSearch
from .service import DocsService
from .store import IndexStore


def parse_duration(value: str) -> float:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*", value)
    if not match:
        raise ValueError(f"invalid duration: {value}")
    multiplier = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
    return float(match.group(1)) * multiplier


def read_sources(path: str | Path) -> list[str]:
    sources: list[str] = []
    for raw_line in Path(path).read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.endswith(("/llms.txt", "/llms-full.txt")):
            raise ValueError(f"source URL must end with /llms.txt or /llms-full.txt: {line}")
        sources.append(line)
    if not sources:
        raise ValueError(f"no sources configured in {path}")
    return list(dict.fromkeys(sources))


def build_server():
    source_file = os.environ.get("DOCS_MCP_SOURCES_FILE", "/etc/context-kit/docs-sources.txt")
    sources = read_sources(source_file)
    store = IndexStore(os.environ.get("DOCS_MCP_STORE_PATH", "/data/docs.sqlite3"))
    store.configure_sources(sources)
    embedder = SentenceTransformerEmbedder(
        os.environ.get("DOCS_MCP_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    )
    fetcher = SourceFetcher(
        timeout_seconds=float(os.environ.get("DOCS_MCP_FETCH_TIMEOUT", "30")),
        max_bytes=int(os.environ.get("DOCS_MCP_MAX_SOURCE_BYTES", "20000000")),
    )
    coordinator = RefreshCoordinator(
        store=store,
        fetcher=fetcher,
        embedder=embedder,
        parser=parse_llms_text,
        ttl_seconds=parse_duration(os.environ.get("DOCS_MCP_TTL", "24h")),
        now=time.time,
    )
    service = DocsService(
        store,
        HybridSearch(store, embedder),
        coordinator,
        max_get_bytes=int(os.environ.get("DOCS_MCP_MAX_GET_BYTES", "75000")),
    )

    mcp = FastMCP(
        "Context Kit Docs",
        instructions="Search and retrieve configured documentation using persisted hybrid retrieval.",
        host=os.environ.get("DOCS_MCP_HTTP_HOST", "0.0.0.0"),
        port=int(os.environ.get("DOCS_MCP_HTTP_PORT", "8000")),
        streamable_http_path="/mcp",
        stateless_http=True,
    )

    @mcp.tool()
    async def docs_query(
        query: str,
        limit: int = 10,
        auto_retrieve: bool = False,
        auto_retrieve_threshold: float = 0.55,
        auto_retrieve_limit: int = 5,
        retrieve_ids: list[str] | None = None,
        max_bytes: int | None = None,
        merge: bool = False,
        sources: list[str] | None = None,
        hosts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search docs. Content retrieval is explicit by default; optionally filter source URLs or hosts."""
        return await service.query(
            query, limit, auto_retrieve, auto_retrieve_threshold, auto_retrieve_limit,
            retrieve_ids, max_bytes, merge, sources, hosts,
        )

    @mcp.tool()
    async def docs_refresh(
        source: str | None = None,
        sources: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Refresh configured sources transactionally; concurrent requests are coalesced."""
        if source and sources:
            raise ValueError("pass source or sources, not both")
        if source:
            sources = [source]
        return await service.refresh(sources, force)

    @mcp.tool()
    async def docs_sources() -> dict[str, Any]:
        """Report configured-source freshness, errors, and document counts."""
        return service.source_status()

    @mcp.tool()
    async def docs_rebuild(
        source: str | None = None,
        sources: list[str] | None = None,
    ) -> dict[str, Any]:
        """Force a safe source rebuild without deleting the last good generation first."""
        if source and sources:
            raise ValueError("pass source or sources, not both")
        if source:
            sources = [source]
        return await service.refresh(sources, force=True)

    app = mcp.streamable_http_app()
    mcp_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def application_lifespan(application):
        preindex_task = None
        async with mcp_lifespan(application):
            if os.environ.get("DOCS_MCP_PREINDEX", "0") == "1":
                preindex_task = asyncio.create_task(service.refresh())
            try:
                yield
            finally:
                if preindex_task:
                    await preindex_task
                await fetcher.close()
                store.close()

    app.router.lifespan_context = application_lifespan

    async def status(_request: Request) -> JSONResponse:
        state = service.source_status()
        errors = sum(1 for source in state["sources"] if source["last_error"])
        return JSONResponse(
            {
                "status": "ok" if state["document_count"] or not errors else "degraded",
                "ready": True,
                "model_ready": embedder.ready,
                "source_count": state["source_count"],
                "document_count": state["document_count"],
                "source_errors": errors,
            }
        )

    app.routes.insert(0, Route("/status", status, methods=["GET"]))
    origins = os.environ.get("DOCS_MCP_ALLOW_ORIGIN", "").split()
    if origins:
        app = CORSMiddleware(app, allow_origins=origins, allow_methods=["POST", "GET", "DELETE"], allow_headers=["*"])
    return app


def main() -> None:
    uvicorn.run(
        build_server(),
        host=os.environ.get("DOCS_MCP_HTTP_HOST", "0.0.0.0"),
        port=int(os.environ.get("DOCS_MCP_HTTP_PORT", "8000")),
        log_level=os.environ.get("DOCS_MCP_LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
