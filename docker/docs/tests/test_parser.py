from __future__ import annotations

import unittest

from context_docs.parser import parse_llms_text


class ParserTest(unittest.TestCase):
    def test_standard_menu_preserves_target_url_and_retrievable_content(self) -> None:
        parsed = parse_llms_text(
            """# Rails Docs

> Curated official documentation.

## Active Record

- [Associations](https://guides.rubyonrails.org/association_basics.html): Model relationships
""",
            "http://127.0.0.1:8769/rails/llms.txt",
        )

        self.assertEqual("standard-menu", parsed.format)
        self.assertEqual(1, len(parsed.documents))
        document = parsed.documents[0]
        self.assertEqual("https://guides.rubyonrails.org/association_basics.html", document.canonical_url)
        self.assertIn("Model relationships", document.content)
        self.assertIn("https://guides.rubyonrails.org/association_basics.html", document.content)

    def test_full_bundle_is_not_misclassified_by_interior_yaml_or_rule(self) -> None:
        parsed = parse_llms_text(
            """# Build a client

Some content.

---
title: This is an embedded example
description: It is not file frontmatter
---

# Elicitation

URL mode details.
""",
            "https://example.test/llms-full.txt",
        )

        self.assertEqual("markdown-full", parsed.format)
        self.assertEqual(["Build a client", "Elicitation"], [doc.title for doc in parsed.documents])

    def test_full_bundle_with_bullet_links_keeps_prose_sections(self) -> None:
        parsed = parse_llms_text(
            """# Persistence

This substantial section explains durable checkpoint behavior.

- [Related guide](https://example.test/guide): Read more

# Streaming

Streaming emits incremental updates.
""",
            "https://example.test/llms-full.txt",
        )

        self.assertEqual("markdown-full", parsed.format)
        self.assertEqual(["Persistence", "Streaming"], [doc.title for doc in parsed.documents])
        self.assertIn("durable checkpoint", parsed.documents[0].content)

    def test_repeated_frontmatter_accepts_optional_description(self) -> None:
        parsed = parse_llms_text(
            """---
title: First
---
First body.
---
title: Second
description: Second description
---
Second body.
""",
            "https://example.test/llms-full.txt",
        )

        self.assertEqual("yaml-full", parsed.format)
        self.assertEqual(["First", "Second"], [doc.title for doc in parsed.documents])
        self.assertEqual("Second description", parsed.documents[1].description)

    def test_long_sections_are_split_without_losing_tail_identifiers(self) -> None:
        body = "Paragraph.\n\n" * 100 + "IMMICH_IGNORE_MOUNT_CHECK_ERRORS disables mount checks."
        parsed = parse_llms_text(
            f"# Environment Variables\n\n{body}",
            "https://example.test/llms-full.txt",
            max_chunk_chars=500,
        )

        self.assertGreater(len(parsed.documents), 1)
        self.assertTrue(any("IMMICH_IGNORE_MOUNT_CHECK_ERRORS" in doc.content for doc in parsed.documents))


if __name__ == "__main__":
    unittest.main()
