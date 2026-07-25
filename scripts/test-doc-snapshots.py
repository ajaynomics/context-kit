#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docs_snapshot import FetchedPage, build_snapshot, page_to_markdown, snapshot_menus, validate_snapshot


class FakeFetcher:
    def __init__(self, pages: dict[str, FetchedPage | Exception]):
        self.pages = pages

    def fetch(self, url: str) -> FetchedPage:
        result = self.pages[url]
        if isinstance(result, Exception):
            raise result
        return result


def page(url: str, body: str, content_type: str = "text/html") -> FetchedPage:
    return FetchedPage(url, url, body.encode(), content_type, '"fixture"', "Wed, 01 Jan 2025 00:00:00 GMT")


class SnapshotTest(unittest.TestCase):
    def test_html_extraction_prefers_main_and_discards_navigation(self) -> None:
        rendered = page_to_markdown(
            page(
                "https://example.test/page",
                "<html><nav>Noise</nav><main><h1>API</h1><p>Useful content.</p></main></html>",
            )
        )
        self.assertNotIn("Noise", rendered)
        self.assertIn("# API", rendered)
        self.assertIn("Useful content.", rendered)

    def test_snapshot_and_manifest_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            menu = Path(directory) / "fixture" / "llms.txt"
            menu.parent.mkdir()
            menu.write_text("# Menu\n\n- [API](https://example.test/api)\n")
            fetcher = FakeFetcher(
                {"https://example.test/api": page("https://example.test/api", "<main><h1>API</h1><p>Stable.</p></main>")}
            )

            first = build_snapshot(menu, fetcher)
            first_output = menu.with_name("llms-full.txt").read_bytes()
            first_manifest = menu.with_name("llms-full.provenance.json").read_bytes()
            second = build_snapshot(menu, fetcher)

            self.assertEqual(first["output_sha256"], second["output_sha256"])
            self.assertEqual(first_output, menu.with_name("llms-full.txt").read_bytes())
            self.assertEqual(first_manifest, menu.with_name("llms-full.provenance.json").read_bytes())
            self.assertEqual(first["output_sha256"], validate_snapshot(menu.with_name("llms-full.txt"))["output_sha256"])

            menu.with_name("llms-full.txt").write_text("tampered\n")
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                validate_snapshot(menu.with_name("llms-full.txt"))

    def test_failed_build_preserves_last_good_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            menu = Path(directory) / "fixture" / "llms.txt"
            menu.parent.mkdir()
            menu.write_text("# Menu\n\n- [API](https://example.test/api)\n")
            output = menu.with_name("llms-full.txt")
            output.write_text("last good\n")

            with self.assertRaisesRegex(RuntimeError, "previous output preserved"):
                build_snapshot(menu, FakeFetcher({"https://example.test/api": RuntimeError("offline")}))

            self.assertEqual("last good\n", output.read_text())

    def test_one_bad_menu_does_not_block_other_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in [
                ("good", "# Menu\n\n- [API](https://example.test/api)\n"),
                ("prose-only", "# Workspace Notes\n\nNo links here, just prose.\n"),
                ("broken", "# Menu\n\n- [Down](https://example.test/down)\n"),
            ]:
                (root / name).mkdir()
                (root / name / "llms.txt").write_text(body)
            fetcher = FakeFetcher({
                "https://example.test/api": page("https://example.test/api", "<main><h1>API</h1><p>Stable.</p></main>"),
                "https://example.test/down": RuntimeError("host unreachable"),
            })

            report = snapshot_menus(sorted(root.glob("*/llms.txt")), fetcher)

            self.assertEqual(1, len(report["snapshots"]))
            self.assertTrue((root / "good" / "llms-full.txt").exists())
            self.assertEqual(1, len(report["skipped"]))
            self.assertIn("prose-only", report["skipped"][0]["menu"])
            self.assertEqual(1, len(report["failures"]))
            self.assertIn("broken", report["failures"][0]["menu"])


if __name__ == "__main__":
    unittest.main()
