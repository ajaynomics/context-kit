from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    description: str
    content: str
    canonical_url: str
    heading_path: str
    chunk_index: int = 0


@dataclass(frozen=True)
class ParsedSource:
    format: str
    documents: list[ParsedDocument]


@dataclass(frozen=True)
class FetchResponse:
    status: int
    requested_url: str
    resolved_url: str
    body: str = ""
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class PreparedDocument:
    id: str
    configured_source: str
    resolved_source: str
    source_host: str
    canonical_url: str
    canonical_host: str
    title: str
    description: str
    heading_path: str
    content: str
    content_hash: str
    embedding: np.ndarray


@dataclass(frozen=True)
class SourceUpdate:
    configured_source: str
    resolved_source: str
    etag: str | None
    last_modified: str | None
    body_hash: str
    raw_body: str
    parser_fingerprint: str
    embedding_fingerprint: str
    checked_at: float
    indexed_at: float
    stale_at: float
    documents: list[PreparedDocument]


@dataclass(frozen=True)
class SourceState:
    configured_source: str
    resolved_source: str | None
    active: bool
    etag: str | None
    last_modified: str | None
    body_hash: str | None
    raw_body: str | None
    parser_fingerprint: str | None
    embedding_fingerprint: str | None
    checked_at: float | None
    indexed_at: float | None
    stale_at: float | None
    last_error: str | None
    doc_count: int


@dataclass(frozen=True)
class StoredDocument:
    id: str
    configured_source: str
    resolved_source: str
    source_host: str
    canonical_url: str
    canonical_host: str
    title: str
    description: str
    heading_path: str
    content: str
    content_hash: str
    embedding: np.ndarray


@dataclass(frozen=True)
class SearchResult:
    id: str
    configured_source: str
    canonical_url: str
    title: str
    description: str
    heading_path: str
    content: str
    content_hash: str
    score: float
    lexical_rank: int | None
    semantic_rank: int | None
    duplicate_count: int = 1
    alternate_sources: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RefreshOutcome:
    source: str
    status: str
    document_count: int
    detail: str | None = None
