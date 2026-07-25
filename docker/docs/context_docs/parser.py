from __future__ import annotations

import re
from urllib.parse import urljoin

import yaml

from .models import ParsedDocument, ParsedSource


PARSER_FINGERPRINT = "context-docs-parser-v1"
_MENU_LINK = re.compile(r"^\s*[-*]\s+\[([^]]+)]\(([^)]+)\)(?::\s*(.*))?\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FRONTMATTER = re.compile(r"(?m)^---\s*$")


def parse_llms_text(content: str, source_url: str, max_chunk_chars: int = 6_000) -> ParsedSource:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ParsedSource("empty", [])

    yaml_documents = _parse_repeated_frontmatter(normalized, source_url, max_chunk_chars)
    if yaml_documents is not None:
        return ParsedSource("yaml-full", yaml_documents)

    if source_url.split("?", 1)[0].endswith("/llms.txt"):
        menu_documents = _parse_menu(normalized, source_url)
        if menu_documents:
            return ParsedSource("standard-menu", menu_documents)

    return ParsedSource("markdown-full", _parse_markdown_bundle(normalized, source_url, max_chunk_chars))


def _parse_repeated_frontmatter(content: str, source_url: str, max_chunk_chars: int) -> list[ParsedDocument] | None:
    if not content.startswith("---\n"):
        return None
    separators = [match.start() for match in _FRONTMATTER.finditer(content)]
    if len(separators) < 2:
        return None

    documents: list[ParsedDocument] = []
    cursor = 0
    while cursor < len(content):
        if not content.startswith("---", cursor):
            return None
        header_end = content.find("\n---", cursor + 3)
        if header_end < 0:
            return None
        try:
            metadata = yaml.safe_load(content[cursor + 3 : header_end]) or {}
        except yaml.YAMLError:
            return None
        if not isinstance(metadata, dict) or not isinstance(metadata.get("title"), str):
            return None
        body_start = header_end + 4
        if body_start < len(content) and content[body_start] == "\n":
            body_start += 1
        next_header = content.find("\n---\n", body_start)
        body_end = len(content) if next_header < 0 else next_header
        body = content[body_start:body_end].strip()
        title = metadata["title"].strip()
        description = str(metadata.get("description") or "").strip()
        canonical = str(metadata.get("url") or metadata.get("canonical_url") or source_url)
        documents.extend(_chunk_document(title, description, body, urljoin(source_url, canonical), title, max_chunk_chars))
        if next_header < 0:
            break
        cursor = next_header + 1
    return documents or None


def _parse_menu(content: str, source_url: str) -> list[ParsedDocument]:
    documents: list[ParsedDocument] = []
    headings: list[tuple[int, str]] = []
    in_fence = False
    for line in content.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            headings = [entry for entry in headings if entry[0] < level]
            headings.append((level, heading.group(2).strip()))
            continue
        link = _MENU_LINK.match(line)
        if not link:
            continue
        title, target, description = link.group(1).strip(), link.group(2).strip(), (link.group(3) or "").strip()
        canonical = urljoin(source_url, target)
        path = " > ".join([name for _, name in headings] + [title])
        rendered = f"{title}\n\n{description}\n\nSource: {canonical}".strip()
        documents.append(ParsedDocument(title, description, rendered, canonical, path))
    return documents


def _parse_markdown_bundle(content: str, source_url: str, max_chunk_chars: int) -> list[ParsedDocument]:
    sections: list[tuple[str, str]] = []
    current_title = "Documentation"
    current_lines: list[str] = []
    in_fence = False
    for line in content.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING.match(line)
        if heading and len(heading.group(1)) == 1:
            if current_lines or sections:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = heading.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines or not sections:
        sections.append((current_title, "\n".join(current_lines).strip()))

    documents: list[ParsedDocument] = []
    for title, body in sections:
        if not body and title == "Documentation":
            continue
        documents.extend(_chunk_document(title, "", body, source_url, title, max_chunk_chars))
    return documents


def _chunk_document(
    title: str,
    description: str,
    content: str,
    canonical_url: str,
    heading_path: str,
    max_chunk_chars: int,
) -> list[ParsedDocument]:
    if len(content) <= max_chunk_chars:
        return [ParsedDocument(title, description, content, canonical_url, heading_path, 0)]

    paragraphs = re.split(r"\n{2,}", content)
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        pieces = [paragraph[index : index + max_chunk_chars] for index in range(0, len(paragraph), max_chunk_chars)] or [""]
        for piece in pieces:
            added = len(piece) + (2 if current else 0)
            if current and size + added > max_chunk_chars:
                chunks.append("\n\n".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece) + (2 if len(current) > 1 else 0)
    if current:
        chunks.append("\n\n".join(current))
    return [
        ParsedDocument(title, description, chunk, canonical_url, heading_path, index)
        for index, chunk in enumerate(chunks)
    ]
