from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from context_docs.models import PreparedDocument, SourceUpdate
from context_docs.store import IndexStore


def document(identifier: str, source: str, title: str, content: str) -> PreparedDocument:
    return PreparedDocument(
        id=identifier,
        configured_source=source,
        resolved_source=source,
        source_host="example.test",
        canonical_url=f"https://docs.example.test/{identifier}",
        canonical_host="docs.example.test",
        title=title,
        description="",
        heading_path=title,
        content=content,
        content_hash=identifier,
        embedding=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
    )


def update(source: str, documents: list[PreparedDocument], checked_at: float = 100.0) -> SourceUpdate:
    return SourceUpdate(
        configured_source=source,
        resolved_source=source,
        etag=None,
        last_modified=None,
        body_hash="body-hash",
        raw_body="# Fixture",
        parser_fingerprint="parser-v1",
        embedding_fingerprint="fake-embedder-v1",
        checked_at=checked_at,
        indexed_at=checked_at,
        stale_at=checked_at + 3600,
        documents=documents,
    )


class StoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "docs.sqlite3"
        self.source = "https://example.test/llms.txt"
        self.store = IndexStore(self.path)
        self.store.configure_sources([self.source])

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_replacement_removes_old_only_documents(self) -> None:
        self.store.replace_source(update(self.source, [document("old", self.source, "Old", "old content")]))
        self.store.replace_source(update(self.source, [document("new", self.source, "New", "new content")]))

        self.assertIsNone(self.store.get_document("old"))
        self.assertEqual("new content", self.store.get_document("new").content)

    def test_failed_replacement_rolls_back_to_previous_generation(self) -> None:
        self.store.replace_source(update(self.source, [document("old", self.source, "Old", "old content")]))
        self.store.connection.execute(
            "CREATE TRIGGER reject_failure BEFORE INSERT ON documents "
            "WHEN NEW.title = 'FAIL' BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )

        with self.assertRaisesRegex(Exception, "injected failure"):
            self.store.replace_source(update(self.source, [document("bad", self.source, "FAIL", "bad")]))

        self.assertEqual("old content", self.store.get_document("old").content)
        self.assertIsNone(self.store.get_document("bad"))

    def test_restart_loads_persisted_state_without_network(self) -> None:
        self.store.replace_source(update(self.source, [document("persisted", self.source, "Persisted", "saved")]))
        self.store.close()

        self.store = IndexStore(self.path)
        self.store.configure_sources([self.source])

        states = self.store.list_sources()
        self.assertEqual(1, states[0].doc_count)
        self.assertEqual("saved", self.store.get_document("persisted").content)

    def test_removed_source_is_not_searchable_or_retrievable(self) -> None:
        self.store.replace_source(update(self.source, [document("retired", self.source, "Retired", "identifier")]))
        self.store.configure_sources([])

        self.assertIsNone(self.store.get_document("retired"))
        self.assertEqual([], self.store.lexical_search("identifier", limit=5))


if __name__ == "__main__":
    unittest.main()
