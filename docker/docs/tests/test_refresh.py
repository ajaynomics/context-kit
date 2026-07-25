from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from context_docs.parser import parse_llms_text
from context_docs.refresh import RefreshCoordinator
from context_docs.store import IndexStore

from .fakes import FakeEmbedder, FakeFetch, FakeFetcher


class RefreshTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.source = "https://example.test/llms.txt"
        self.store = IndexStore(Path(self.tmp.name) / "docs.sqlite3")
        self.store.configure_sources([self.source])

    async def asyncTearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    async def test_concurrent_refresh_uses_one_fetch_and_one_publication(self) -> None:
        fetcher = FakeFetcher([FakeFetch(200, "# API Identifier\n\nExact identifier content.")])
        coordinator = RefreshCoordinator(
            store=self.store,
            fetcher=fetcher,
            embedder=FakeEmbedder(),
            parser=parse_llms_text,
            ttl_seconds=3600,
            now=lambda: 100.0,
        )

        first, second = await asyncio.gather(
            coordinator.refresh(self.source, force=True),
            coordinator.refresh(self.source, force=True),
        )

        self.assertEqual(1, fetcher.calls)
        self.assertEqual("updated", first.status)
        self.assertEqual("updated", second.status)
        self.assertEqual(1, self.store.list_sources()[0].doc_count)

    async def test_304_updates_check_time_without_replacing_documents(self) -> None:
        fetcher = FakeFetcher(
            [
                FakeFetch(200, "# API Identifier\n\nOriginal content.", etag='"v1"'),
                FakeFetch(304, etag='"v1"'),
            ]
        )
        clock = iter([100.0, 200.0])
        coordinator = RefreshCoordinator(
            store=self.store,
            fetcher=fetcher,
            embedder=FakeEmbedder(),
            parser=parse_llms_text,
            ttl_seconds=3600,
            now=lambda: next(clock),
        )
        await coordinator.refresh(self.source, force=True)
        original = self.store.list_sources()[0]
        await coordinator.refresh(self.source, force=True)
        checked = self.store.list_sources()[0]

        self.assertEqual(original.indexed_at, checked.indexed_at)
        self.assertEqual(200.0, checked.checked_at)
        self.assertEqual(1, checked.doc_count)

    async def test_refresh_error_preserves_searchable_previous_content(self) -> None:
        fetcher = FakeFetcher(
            [
                FakeFetch(200, "# API Identifier\n\nOriginal content."),
                FakeFetch(500),
            ]
        )
        coordinator = RefreshCoordinator(
            store=self.store,
            fetcher=fetcher,
            embedder=FakeEmbedder(),
            parser=parse_llms_text,
            ttl_seconds=3600,
            now=lambda: 100.0,
        )
        await coordinator.refresh(self.source, force=True)
        failed = await coordinator.refresh(self.source, force=True)

        self.assertEqual("error", failed.status)
        self.assertEqual(1, self.store.list_sources()[0].doc_count)
        self.assertTrue(self.store.lexical_search("Original", limit=5))

    async def test_empty_success_response_preserves_previous_content(self) -> None:
        fetcher = FakeFetcher(
            [
                FakeFetch(200, "# API Identifier\n\nOriginal content."),
                FakeFetch(200, ""),
            ]
        )
        coordinator = RefreshCoordinator(
            store=self.store,
            fetcher=fetcher,
            embedder=FakeEmbedder(),
            parser=parse_llms_text,
            ttl_seconds=3600,
            now=lambda: 100.0,
        )
        await coordinator.refresh(self.source, force=True)
        failed = await coordinator.refresh(self.source, force=True)

        self.assertEqual("error", failed.status)
        self.assertIn("zero documents", failed.detail)
        self.assertTrue(self.store.lexical_search("Original", limit=5))


if __name__ == "__main__":
    unittest.main()
