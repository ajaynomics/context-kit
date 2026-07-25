#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.error import HTTPError
from urllib.request import Request, urlopen


GENERATOR_VERSION = "1"
_LINK = re.compile(r"^\s*[-*]\s+\[([^]]+)]\(([^)]+)\)(?::\s*(.*))?\s*$")


@dataclass(frozen=True)
class MenuEntry:
    title: str
    url: str
    description: str


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    resolved_url: str
    body: bytes
    content_type: str
    etag: str | None
    last_modified: str | None


def parse_menu(content: str, source_url: str = "") -> list[MenuEntry]:
    entries: list[MenuEntry] = []
    for line in content.splitlines():
        match = _LINK.match(line)
        if match:
            entries.append(
                MenuEntry(
                    title=match.group(1).strip(),
                    url=urljoin(source_url, match.group(2).strip()),
                    description=(match.group(3) or "").strip(),
                )
            )
    return entries


class _ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.all_parts: list[str] = []
        self.main_parts: list[str] = []
        self.main_depth = 0
        self.skip_depth = 0
        self.heading_level = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "svg", "noscript", "nav", "footer"}:
            self.skip_depth += 1
            return
        if tag in {"main", "article"}:
            self.main_depth += 1
        if self.skip_depth:
            return
        if tag in {"p", "div", "section", "br", "table", "tr", "pre"}:
            self._append("\n")
        elif tag == "li":
            self._append("\n- ")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_level = int(tag[1])
            self._append(f"\n\n{'#' * self.heading_level} ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "svg", "noscript", "nav", "footer"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if not self.skip_depth and tag in {"p", "div", "section", "li", "tr", "pre", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._append("\n")
        if tag in {"main", "article"} and self.main_depth:
            self.main_depth -= 1
        if tag.startswith("h"):
            self.heading_level = 0

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self._append(data)

    def _append(self, text: str) -> None:
        self.all_parts.append(text)
        if self.main_depth:
            self.main_parts.append(text)

    def rendered(self) -> str:
        preferred = self.main_parts if any(part.strip() for part in self.main_parts) else self.all_parts
        text = html.unescape("".join(preferred)).replace("\r", "")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def page_to_markdown(page: FetchedPage) -> str:
    text = page.body.decode("utf-8", errors="replace")
    content_type = page.content_type.lower()
    if "html" not in content_type and not re.search(r"<html|<main|<article", text[:1000], re.I):
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()
    parser = _ReadableHTML()
    parser.feed(text)
    return parser.rendered()


class CachedFetcher:
    def __init__(self, cache_dir: Path, offline: bool = False, timeout: float = 30):
        self.cache_dir = cache_dir
        self.offline = offline
        self.timeout = timeout
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        return None

    def fetch(self, url: str) -> FetchedPage:
        key = hashlib.sha256(url.encode()).hexdigest()
        body_path = self.cache_dir / f"{key}.body"
        metadata_path = self.cache_dir / f"{key}.json"
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        if self.offline:
            if not body_path.exists():
                raise RuntimeError(f"offline cache miss: {url}")
            return self._cached(url, body_path, metadata)

        headers = {}
        if metadata.get("etag"):
            headers["If-None-Match"] = metadata["etag"]
        if metadata.get("last_modified"):
            headers["If-Modified-Since"] = metadata["last_modified"]
        headers["User-Agent"] = "context-kit-snapshot/1.0"
        try:
            response = urlopen(Request(url, headers=headers), timeout=self.timeout)
        except HTTPError as error:
            if error.code != 304:
                raise
            response = error
        if response.status == 304:
            if not body_path.exists():
                raise RuntimeError(f"HTTP 304 without cached body: {url}")
            return self._cached(url, body_path, metadata)
        body = response.read()
        metadata = {
            "requested_url": url,
            "resolved_url": response.geturl(),
            "content_type": response.headers.get("content-type", ""),
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
        atomic_write(body_path, body)
        atomic_write(metadata_path, (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode())
        return self._cached(url, body_path, metadata)

    @staticmethod
    def _cached(url: str, body_path: Path, metadata: dict) -> FetchedPage:
        return FetchedPage(
            requested_url=url,
            resolved_url=metadata.get("resolved_url", url),
            body=body_path.read_bytes(),
            content_type=metadata.get("content_type", "text/plain"),
            etag=metadata.get("etag"),
            last_modified=metadata.get("last_modified"),
        )


def build_snapshot(menu_path: Path, fetcher) -> dict:
    menu = menu_path.read_text()
    entries = parse_menu(menu)
    if not entries:
        raise RuntimeError(f"no markdown links in {menu_path}")
    sections: list[str] = []
    documents: list[dict] = []
    failures: list[str] = []
    for entry in entries:
        try:
            page = fetcher.fetch(entry.url)
            content = page_to_markdown(page)
            if not content:
                raise RuntimeError("extracted content is empty")
            sections.append(f"# {entry.title}\n\nSource: {page.resolved_url}\n\n{content}")
            documents.append(
                {
                    "title": entry.title,
                    "requested_url": entry.url,
                    "resolved_url": page.resolved_url,
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "source_sha256": hashlib.sha256(page.body).hexdigest(),
                    "etag": page.etag,
                    "last_modified": page.last_modified,
                }
            )
        except Exception as error:
            failures.append(f"{entry.url}: {error}")
    if failures:
        raise RuntimeError("snapshot fetch failed; previous output preserved:\n" + "\n".join(failures))

    output = ("\n\n".join(sections).strip() + "\n").encode()
    manifest = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "menu": menu_path.name,
        "menu_sha256": hashlib.sha256(menu.encode()).hexdigest(),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "document_count": len(documents),
        "documents": documents,
    }
    output_path = menu_path.with_name("llms-full.txt")
    manifest_path = menu_path.with_name("llms-full.provenance.json")
    atomic_write(output_path, output)
    atomic_write(manifest_path, (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
    return {"menu": str(menu_path), "output": str(output_path), **manifest}


def validate_snapshot(output_path: Path) -> dict:
    manifest_path = output_path.with_name("llms-full.provenance.json")
    if not output_path.is_file() or not manifest_path.is_file():
        raise RuntimeError("snapshot or provenance manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    output_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
    if manifest.get("output_sha256") != output_hash:
        raise RuntimeError("snapshot hash does not match provenance manifest")
    menu_path = output_path.with_name(str(manifest.get("menu") or "llms.txt"))
    if not menu_path.is_file():
        raise RuntimeError("snapshot source menu is missing")
    menu_hash = hashlib.sha256(menu_path.read_bytes()).hexdigest()
    if manifest.get("menu_sha256") != menu_hash:
        raise RuntimeError("menu hash does not match provenance manifest")
    return manifest


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def snapshot_menus(menus: list[Path], fetcher) -> dict:
    """Snapshot every menu independently so one bad directory cannot block the rest."""
    report: dict = {"snapshots": [], "skipped": [], "failures": []}
    for menu in menus:
        if not parse_menu(menu.read_text()):
            report["skipped"].append({"menu": str(menu), "reason": "no markdown links"})
            continue
        try:
            report["snapshots"].append(build_snapshot(menu, fetcher))
        except Exception as error:
            report["failures"].append({"menu": str(menu), "error": str(error)})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic content snapshots from local llms.txt menus.")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--validate-output", type=Path)
    args = parser.parse_args()
    if args.validate_output:
        print(json.dumps(validate_snapshot(args.validate_output), sort_keys=True))
        return
    if not args.source_root:
        parser.error("--source-root is required unless --validate-output is used")
    cache_dir = args.cache_dir or args.source_root / ".snapshot-cache"
    menus = sorted(args.source_root.glob("*/llms.txt"))
    if args.only:
        selected = set(args.only)
        menus = [menu for menu in menus if menu.parent.name in selected]
    if not menus:
        raise SystemExit("no matching llms.txt menus")

    fetcher = CachedFetcher(cache_dir, offline=args.offline)
    try:
        report = snapshot_menus(menus, fetcher)
    finally:
        fetcher.close()
    print(json.dumps(report, sort_keys=True, indent=2))
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
