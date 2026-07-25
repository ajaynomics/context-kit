from __future__ import annotations

from collections import defaultdict

import numpy as np

from .models import SearchResult, StoredDocument
from .store import IndexStore


class HybridSearch:
    def __init__(self, store: IndexStore, embedder, rrf_k: int = 60):
        self.store = store
        self.embedder = embedder
        self.rrf_k = rrf_k

    async def search(
        self,
        query: str,
        limit: int = 10,
        sources: list[str] | None = None,
        hosts: list[str] | None = None,
    ) -> list[SearchResult]:
        pool_size = max(limit * 8, 40)
        lexical = self.store.lexical_search(query, pool_size, sources, hosts)
        candidates = self.store.semantic_candidates(sources, hosts)
        semantic: list[StoredDocument] = []
        if candidates:
            query_vector = np.asarray(await self.embedder.encode_query(query), dtype=np.float32)
            query_norm = np.linalg.norm(query_vector)
            scored: list[tuple[float, StoredDocument]] = []
            for document in candidates:
                norm = np.linalg.norm(document.embedding) * query_norm
                score = float(np.dot(document.embedding, query_vector) / norm) if norm else 0.0
                scored.append((score, document))
            semantic = [document for _, document in sorted(scored, key=lambda item: (-item[0], item[1].id))[:pool_size]]

        lexical_ranks = {document.id: rank for rank, document in enumerate(lexical, 1)}
        semantic_ranks = {document.id: rank for rank, document in enumerate(semantic, 1)}
        documents = {document.id: document for document in [*lexical, *semantic]}
        scores = defaultdict(float)
        for identifier, rank in lexical_ranks.items():
            scores[identifier] += 1.0 / (self.rrf_k + rank)
        for identifier, rank in semantic_ranks.items():
            scores[identifier] += 1.0 / (self.rrf_k + rank)

        ordered = sorted(documents.values(), key=lambda item: (-scores[item.id], item.id))
        groups: dict[str, list[StoredDocument]] = {}
        group_order: list[str] = []
        for document in ordered:
            key = document.content_hash
            if key not in groups:
                groups[key] = []
                group_order.append(key)
            groups[key].append(document)

        results: list[SearchResult] = []
        for key in group_order[:limit]:
            group = groups[key]
            primary = group[0]
            alternates = [
                {"source": document.configured_source, "url": document.canonical_url}
                for document in group[1:]
            ]
            results.append(
                SearchResult(
                    id=primary.id,
                    configured_source=primary.configured_source,
                    canonical_url=primary.canonical_url,
                    title=primary.title,
                    description=primary.description,
                    heading_path=primary.heading_path,
                    content=primary.content,
                    content_hash=primary.content_hash,
                    score=min(1.0, scores[primary.id] / (2.0 / (self.rrf_k + 1))),
                    lexical_rank=lexical_ranks.get(primary.id),
                    semantic_rank=semantic_ranks.get(primary.id),
                    duplicate_count=len(group),
                    alternate_sources=alternates,
                )
            )
        return results
