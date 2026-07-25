from __future__ import annotations

import asyncio
import hashlib
from urllib.parse import urlparse

from .models import PreparedDocument, RefreshOutcome, SourceUpdate
from .parser import PARSER_FINGERPRINT


class RefreshCoordinator:
    def __init__(self, store, fetcher, embedder, parser, ttl_seconds: float, now):
        self.store = store
        self.fetcher = fetcher
        self.embedder = embedder
        self.parser = parser
        self.ttl_seconds = ttl_seconds
        self.now = now
        self._inflight: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def refresh(self, source: str, force: bool = False) -> RefreshOutcome:
        state = self.store.get_source(source)
        timestamp = self.now()
        compatible = bool(
            state
            and state.parser_fingerprint == PARSER_FINGERPRINT
            and state.embedding_fingerprint == self.embedder.fingerprint
        )
        if not force and compatible and state.doc_count and state.stale_at and state.stale_at > timestamp:
            return RefreshOutcome(source, "fresh", state.doc_count)

        async with self._lock:
            task = self._inflight.get(source)
            if task is None:
                task = asyncio.create_task(self._refresh_once(source, timestamp))
                self._inflight[source] = task
        try:
            return await task
        finally:
            async with self._lock:
                if self._inflight.get(source) is task and task.done():
                    self._inflight.pop(source, None)

    async def _refresh_once(self, source: str, timestamp: float) -> RefreshOutcome:
        state = self.store.get_source(source)
        try:
            compatible = bool(
                state
                and state.parser_fingerprint == PARSER_FINGERPRINT
                and state.embedding_fingerprint == self.embedder.fingerprint
            )
            response = await self.fetcher.fetch(source, state if compatible else None)
            if response.status == 304:
                count = state.doc_count if state else 0
                self.store.mark_checked(source, timestamp, timestamp + self.ttl_seconds)
                return RefreshOutcome(source, "not_modified", count)
            if response.status != 200:
                raise RuntimeError(f"source returned HTTP {response.status}")

            parsed = self.parser(response.body, response.resolved_url)
            if not parsed.documents:
                raise RuntimeError("source parsed to zero documents; previous generation preserved")
            texts = ["\n\n".join(filter(None, [doc.title, doc.description, doc.heading_path, doc.content])) for doc in parsed.documents]
            vectors = await self.embedder.encode_documents(texts) if texts else []
            documents: list[PreparedDocument] = []
            source_host = (urlparse(response.resolved_url).hostname or "").lower()
            for parsed_document, vector in zip(parsed.documents, vectors, strict=True):
                content_hash = hashlib.sha256(parsed_document.content.encode()).hexdigest()
                identity = "\0".join(
                    [source, parsed_document.canonical_url, parsed_document.heading_path, str(parsed_document.chunk_index)]
                )
                documents.append(
                    PreparedDocument(
                        id=hashlib.sha256(identity.encode()).hexdigest()[:24],
                        configured_source=source,
                        resolved_source=response.resolved_url,
                        source_host=source_host,
                        canonical_url=parsed_document.canonical_url,
                        canonical_host=(urlparse(parsed_document.canonical_url).hostname or source_host).lower(),
                        title=parsed_document.title,
                        description=parsed_document.description,
                        heading_path=parsed_document.heading_path,
                        content=parsed_document.content,
                        content_hash=content_hash,
                        embedding=vector,
                    )
                )
            body_hash = hashlib.sha256(response.body.encode()).hexdigest()
            self.store.replace_source(
                SourceUpdate(
                    configured_source=source,
                    resolved_source=response.resolved_url,
                    etag=response.etag,
                    last_modified=response.last_modified,
                    body_hash=body_hash,
                    raw_body=response.body,
                    parser_fingerprint=PARSER_FINGERPRINT,
                    embedding_fingerprint=self.embedder.fingerprint,
                    checked_at=timestamp,
                    indexed_at=timestamp,
                    stale_at=timestamp + self.ttl_seconds,
                    documents=documents,
                )
            )
            return RefreshOutcome(source, "updated", len(documents), parsed.format)
        except Exception as error:
            self.store.mark_checked(source, timestamp, timestamp, str(error))
            return RefreshOutcome(source, "error", state.doc_count if state else 0, str(error))
