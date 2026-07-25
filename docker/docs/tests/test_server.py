from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from context_docs.server import build_server, parse_duration, read_sources


class ServerTest(unittest.TestCase):
    def test_duration_parser_rejects_ambiguous_values(self) -> None:
        self.assertEqual(86_400, parse_duration("24h"))
        with self.assertRaises(ValueError):
            parse_duration("tomorrow")

    def test_source_file_requires_supported_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.txt"
            path.write_text("https://example.test/index.html\n")
            with self.assertRaisesRegex(ValueError, "must end"):
                read_sources(path)

    def test_status_is_available_without_loading_embedding_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / "sources.txt"
            source_file.write_text("https://example.test/llms.txt\n")
            environment = {
                "DOCS_MCP_SOURCES_FILE": str(source_file),
                "DOCS_MCP_STORE_PATH": str(Path(directory) / "docs.sqlite3"),
                "DOCS_MCP_PREINDEX": "0",
            }
            with patch.dict(os.environ, environment, clear=False):
                with TestClient(build_server()) as client:
                    response = client.get("/status")

            self.assertEqual(200, response.status_code)
            self.assertTrue(response.json()["ready"])
            self.assertFalse(response.json()["model_ready"])


if __name__ == "__main__":
    unittest.main()
