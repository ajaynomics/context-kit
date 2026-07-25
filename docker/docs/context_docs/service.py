from __future__ import annotations

import asyncio
from dataclasses import asdict


class DocsService:
    def __init__(self, store, search, refresh, max_get_bytes: int = 75_000):
        self.store = store
        self.search_engine = search
        self.refresh_coordinator = refresh
        self.max_get_bytes = max_get_bytes

    async def refresh(self, sources: list[str] | None = None, force: bool = False) -> dict:
        configured = [state.configured_source for state in self.store.list_sources()]
        selected = configured if sources is None else sources
        unknown = sorted(set(selected) - set(configured))
        if unknown:
            raise ValueError(f"unconfigured sources: {', '.join(unknown)}")
        outcomes = await asyncio.gather(
            *(self.refresh_coordinator.refresh(source, force=force) for source in selected)
        )
        return {"sources": [asdict(outcome) for outcome in outcomes]}

    async def query(
        self,
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
    ) -> dict:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if not 0 <= auto_retrieve_threshold <= 1:
            raise ValueError("auto_retrieve_threshold must be between 0 and 1")
        if not 0 <= auto_retrieve_limit <= 25:
            raise ValueError("auto_retrieve_limit must be between 0 and 25")

        await self._refresh_missing_or_stale(sources)
        results = await self.search_engine.search(query, limit, sources, hosts)
        search_results = [
            {
                "id": item.id,
                "source": item.configured_source,
                "url": item.canonical_url,
                "host": item.canonical_url.split("/", 3)[2] if "://" in item.canonical_url else "",
                "title": item.title,
                "description": item.description,
                "heading_path": item.heading_path,
                "score": round(item.score, 6),
                "snippet": item.content[:500],
                "duplicate_count": item.duplicate_count,
                "alternate_sources": item.alternate_sources,
            }
            for item in results
        ]

        selected_ids = list(dict.fromkeys(retrieve_ids or []))
        if auto_retrieve:
            selected_ids.extend(
                item.id
                for item in results[:auto_retrieve_limit]
                if item.score >= auto_retrieve_threshold and item.id not in selected_ids
            )
        byte_budget = min(max_bytes or self.max_get_bytes, self.max_get_bytes)
        retrieved: dict[str, dict] = {}
        used = 0
        for identifier in selected_ids[:25]:
            document = self.store.get_document(identifier, sources, hosts)
            if not document:
                continue
            encoded = document.content.encode()
            remaining = max(0, byte_budget - used)
            if remaining == 0:
                break
            content = encoded[:remaining].decode(errors="ignore")
            used += len(content.encode())
            retrieved[identifier] = {
                "id": identifier,
                "source": document.configured_source,
                "url": document.canonical_url,
                "title": document.title,
                "content": content,
                "truncated": len(content.encode()) < len(encoded),
            }

        merged = ""
        if merge:
            merged = "\n\n".join(
                f"# {item['title']}\n\nSource: {item['url']}\n\n{item['content']}"
                for item in retrieved.values()
            )
        return {
            "search_results": search_results,
            "retrieved_content": retrieved,
            "merged_content": merged,
            "auto_retrieved_count": len(retrieved) - len([item for item in retrieve_ids or [] if item in retrieved]),
            "total_results": len(search_results),
        }

    async def _refresh_missing_or_stale(self, sources: list[str] | None) -> None:
        states = self.store.list_sources()
        selected = [state for state in states if sources is None or state.configured_source in sources]
        await asyncio.gather(
            *(self.refresh_coordinator.refresh(state.configured_source) for state in selected)
        )

    def source_status(self) -> dict:
        states = [asdict(state) for state in self.store.list_sources()]
        for state in states:
            state.pop("raw_body", None)
        return {
            "sources": states,
            "source_count": len(states),
            "document_count": sum(state["doc_count"] for state in states),
        }
