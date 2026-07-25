from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from context_docs.models import PreparedDocument, RefreshOutcome, SourceUpdate
from context_docs.search import HybridSearch
from context_docs.service import DocsService
from context_docs.store import IndexStore

from .fakes import FakeEmbedder


class NoopRefresh:
    async def refresh(self, source: str, force: bool = False) -> RefreshOutcome:
        return RefreshOutcome(source, "fresh", 1)


class ServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = IndexStore(Path(self.tmp.name) / "docs.sqlite3")
        self.source = "https://example.test/llms.txt"
        self.store.configure_sources([self.source])
        content = "IMMICH_IGNORE_MOUNT_CHECK_ERRORS " + "x" * 200
        item = PreparedDocument(
            id="exact",
            configured_source=self.source,
            resolved_source=self.source,
            source_host="example.test",
            canonical_url="https://docs.example.test/environment",
            canonical_host="docs.example.test",
            title="Environment",
            description="",
            heading_path="Environment",
            content=content,
            content_hash="content-hash",
            embedding=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        )
        self.store.replace_source(
            SourceUpdate(
                configured_source=self.source,
                resolved_source=self.source,
                etag=None,
                last_modified=None,
                body_hash="body",
                raw_body="# body",
                parser_fingerprint="context-docs-parser-v1",
                embedding_fingerprint="fake-embedder-v1",
                checked_at=1.0,
                indexed_at=1.0,
                stale_at=9_999_999_999.0,
                documents=[item],
            )
        )
        embedder = FakeEmbedder()
        self.service = DocsService(
            self.store,
            HybridSearch(self.store, embedder),
            NoopRefresh(),
            max_get_bytes=100,
        )

    async def asyncTearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    async def test_query_does_not_retrieve_content_by_default(self) -> None:
        response = await self.service.query("IMMICH_IGNORE_MOUNT_CHECK_ERRORS")

        self.assertEqual({}, response["retrieved_content"])
        self.assertEqual("exact", response["search_results"][0]["id"])

    async def test_explicit_retrieval_respects_global_byte_cap(self) -> None:
        response = await self.service.query(
            "IMMICH_IGNORE_MOUNT_CHECK_ERRORS",
            retrieve_ids=["exact"],
            max_bytes=10_000,
        )
        retrieved = response["retrieved_content"]["exact"]

        self.assertLessEqual(len(retrieved["content"].encode()), 100)
        self.assertTrue(retrieved["truncated"])

    async def test_high_default_threshold_only_retrieves_strong_hybrid_match(self) -> None:
        response = await self.service.query(
            "IMMICH_IGNORE_MOUNT_CHECK_ERRORS",
            auto_retrieve=True,
        )

        self.assertIn("exact", response["retrieved_content"])


if __name__ == "__main__":
    unittest.main()
