from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from context_docs.models import PreparedDocument, SourceUpdate
from context_docs.search import HybridSearch
from context_docs.store import IndexStore

from .fakes import FakeEmbedder


def prepared(identifier: str, source: str, canonical: str, title: str, content: str, vector) -> PreparedDocument:
    return PreparedDocument(
        id=identifier,
        configured_source=source,
        resolved_source=source,
        source_host="source.test",
        canonical_url=canonical,
        canonical_host=canonical.split("/")[2],
        title=title,
        description="",
        heading_path=title,
        content=content,
        content_hash=__import__("hashlib").sha256(content.encode()).hexdigest(),
        embedding=np.asarray(vector, dtype=np.float32),
    )


def source_update(source: str, documents: list[PreparedDocument]) -> SourceUpdate:
    return SourceUpdate(
        configured_source=source,
        resolved_source=source,
        etag=None,
        last_modified=None,
        body_hash="body",
        raw_body="# source",
        parser_fingerprint="parser-v1",
        embedding_fingerprint="fake-embedder-v1",
        checked_at=1.0,
        indexed_at=1.0,
        stale_at=9999.0,
        documents=documents,
    )


class HybridSearchTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = IndexStore(Path(self.tmp.name) / "docs.sqlite3")
        self.a = "https://a.test/llms.txt"
        self.b = "https://b.test/llms.txt"
        self.store.configure_sources([self.a, self.b])
        duplicate = "Shared exact content."
        self.store.replace_source(
            source_update(
                self.a,
                [
                    prepared("exact", self.a, "https://rails.test/exact", "Environment", "IMMICH_IGNORE_MOUNT_CHECK_ERRORS identifier", [1, 0, 0, 0]),
                    prepared("duplicate-a", self.a, "https://docs.test/shared", "Shared", duplicate, [0, 1, 0, 0]),
                ],
            )
        )
        self.store.replace_source(
            source_update(
                self.b,
                [
                    prepared("persistence", self.b, "https://langgraph.test/persistence", "Persistence", "Durable checkpoint state", [0, 1, 0, 0]),
                    prepared("duplicate-b", self.b, "https://docs.test/shared-copy", "Shared copy", duplicate, [0, 1, 0, 0]),
                ],
            )
        )
        self.search = HybridSearch(self.store, FakeEmbedder())

    async def asyncTearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    async def test_exact_identifier_is_ranked_first(self) -> None:
        result = await self.search.search("IMMICH_IGNORE_MOUNT_CHECK_ERRORS", limit=5)
        self.assertEqual("exact", result[0].id)
        self.assertEqual(1, result[0].lexical_rank)

    async def test_source_and_host_filters_apply_before_ranking(self) -> None:
        by_source = await self.search.search("persistence", limit=5, sources=[self.b])
        by_host = await self.search.search("identifier", limit=5, hosts=["rails.test"])

        self.assertTrue(by_source)
        self.assertTrue(all(item.configured_source == self.b for item in by_source))
        self.assertEqual(["exact"], [item.id for item in by_host])

    async def test_exact_duplicate_content_is_collapsed_with_alternates(self) -> None:
        result = await self.search.search("Shared exact content", limit=10)
        shared = [item for item in result if item.content_hash == __import__("hashlib").sha256("Shared exact content.".encode()).hexdigest()]

        self.assertEqual(1, len(shared))
        self.assertEqual(2, shared[0].duplicate_count)
        self.assertEqual(1, len(shared[0].alternate_sources))


if __name__ == "__main__":
    unittest.main()
