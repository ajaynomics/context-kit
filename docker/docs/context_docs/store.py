from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

import numpy as np

from .models import PreparedDocument, SourceState, SourceUpdate, StoredDocument


class IndexStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA busy_timeout=5000")
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                  configured_source TEXT PRIMARY KEY,
                  resolved_source TEXT,
                  active INTEGER NOT NULL DEFAULT 1,
                  etag TEXT,
                  last_modified TEXT,
                  body_hash TEXT,
                  raw_body TEXT,
                  parser_fingerprint TEXT,
                  embedding_fingerprint TEXT,
                  checked_at REAL,
                  indexed_at REAL,
                  stale_at REAL,
                  last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS documents (
                  id TEXT PRIMARY KEY,
                  configured_source TEXT NOT NULL REFERENCES sources(configured_source) ON DELETE CASCADE,
                  resolved_source TEXT NOT NULL,
                  source_host TEXT NOT NULL,
                  canonical_url TEXT NOT NULL,
                  canonical_host TEXT NOT NULL,
                  title TEXT NOT NULL,
                  description TEXT NOT NULL,
                  heading_path TEXT NOT NULL,
                  content TEXT NOT NULL,
                  content_hash TEXT NOT NULL,
                  embedding BLOB NOT NULL,
                  embedding_dim INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS documents_source ON documents(configured_source);
                CREATE INDEX IF NOT EXISTS documents_hash ON documents(content_hash);
                CREATE INDEX IF NOT EXISTS documents_hosts ON documents(source_host, canonical_host);
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                  doc_id UNINDEXED, title, description, heading_path, content, canonical_url,
                  tokenize='unicode61 remove_diacritics 2 tokenchars ''_-'''
                );
                """
            )

    def close(self) -> None:
        self.connection.close()

    def configure_sources(self, sources: list[str]) -> None:
        with self._lock, self.connection:
            self.connection.execute("UPDATE sources SET active = 0")
            self.connection.executemany(
                "INSERT INTO sources(configured_source, active) VALUES(?, 1) "
                "ON CONFLICT(configured_source) DO UPDATE SET active = 1",
                [(source,) for source in dict.fromkeys(sources)],
            )

    def replace_source(self, update: SourceUpdate) -> None:
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                self._replace_source(update)
            except Exception:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def _replace_source(self, update: SourceUpdate) -> None:
        self.connection.execute(
                """INSERT INTO sources(
                     configured_source, resolved_source, active, etag, last_modified,
                     body_hash, raw_body, parser_fingerprint, embedding_fingerprint,
                     checked_at, indexed_at, stale_at, last_error
                   ) VALUES(?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                   ON CONFLICT(configured_source) DO UPDATE SET
                     resolved_source=excluded.resolved_source, etag=excluded.etag,
                     last_modified=excluded.last_modified, body_hash=excluded.body_hash,
                     raw_body=excluded.raw_body, parser_fingerprint=excluded.parser_fingerprint,
                     embedding_fingerprint=excluded.embedding_fingerprint,
                     checked_at=excluded.checked_at, indexed_at=excluded.indexed_at,
                     stale_at=excluded.stale_at, last_error=NULL""",
                (
                    update.configured_source,
                    update.resolved_source,
                    update.etag,
                    update.last_modified,
                    update.body_hash,
                    update.raw_body,
                    update.parser_fingerprint,
                    update.embedding_fingerprint,
                    update.checked_at,
                    update.indexed_at,
                    update.stale_at,
                ),
        )
        old_ids = [row[0] for row in self.connection.execute("SELECT id FROM documents WHERE configured_source=?", (update.configured_source,))]
        if old_ids:
            self.connection.executemany("DELETE FROM documents_fts WHERE doc_id=?", [(identifier,) for identifier in old_ids])
        self.connection.execute("DELETE FROM documents WHERE configured_source=?", (update.configured_source,))
        for document in update.documents:
            vector = np.asarray(document.embedding, dtype=np.float32)
            self.connection.execute(
                    """INSERT INTO documents VALUES(
                         ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                       )""",
                    (
                        document.id,
                        document.configured_source,
                        document.resolved_source,
                        document.source_host,
                        document.canonical_url,
                        document.canonical_host,
                        document.title,
                        document.description,
                        document.heading_path,
                        document.content,
                        document.content_hash,
                        vector.tobytes(),
                        vector.size,
                    ),
            )
            self.connection.execute(
                "INSERT INTO documents_fts VALUES(?, ?, ?, ?, ?, ?)",
                (
                    document.id,
                    document.title,
                    document.description,
                    document.heading_path,
                    document.content,
                    document.canonical_url,
                ),
            )

    def mark_checked(self, source: str, checked_at: float, stale_at: float, error: str | None = None) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "UPDATE sources SET checked_at=?, stale_at=?, last_error=? WHERE configured_source=?",
                (checked_at, stale_at, error, source),
            )

    def list_sources(self, include_inactive: bool = False) -> list[SourceState]:
        condition = "" if include_inactive else "WHERE s.active=1"
        rows = self.connection.execute(
            f"""SELECT s.*, COUNT(d.id) AS doc_count FROM sources s
                LEFT JOIN documents d ON d.configured_source=s.configured_source
                {condition} GROUP BY s.configured_source ORDER BY s.configured_source"""
        ).fetchall()
        return [self._source(row) for row in rows]

    def get_source(self, source: str) -> SourceState | None:
        row = self.connection.execute(
            """SELECT s.*, COUNT(d.id) AS doc_count FROM sources s
               LEFT JOIN documents d ON d.configured_source=s.configured_source
               WHERE s.configured_source=? GROUP BY s.configured_source""",
            (source,),
        ).fetchone()
        return self._source(row) if row else None

    def get_document(
        self,
        identifier: str,
        sources: list[str] | None = None,
        hosts: list[str] | None = None,
    ) -> StoredDocument | None:
        where, parameters = self._filters(sources, hosts, alias="d")
        row = self.connection.execute(
            f"SELECT d.* FROM documents d JOIN sources s ON s.configured_source=d.configured_source "
            f"WHERE s.active=1 AND d.id=? {where}",
            [identifier, *parameters],
        ).fetchone()
        return self._document(row) if row else None

    def lexical_search(
        self,
        query: str,
        limit: int,
        sources: list[str] | None = None,
        hosts: list[str] | None = None,
    ) -> list[StoredDocument]:
        terms = re.findall(r"[\w.-]+", query, flags=re.UNICODE)
        if not terms:
            return []
        expression = " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
        where, parameters = self._filters(sources, hosts, alias="d")
        rows = self.connection.execute(
            f"""SELECT d.* FROM documents_fts f
                JOIN documents d ON d.id=f.doc_id
                JOIN sources s ON s.configured_source=d.configured_source
                WHERE documents_fts MATCH ? AND s.active=1 {where}
                ORDER BY bm25(documents_fts, 0, 8, 3, 5, 1, 2) LIMIT ?""",
            [expression, *parameters, limit],
        ).fetchall()
        return [self._document(row) for row in rows]

    def semantic_candidates(
        self,
        sources: list[str] | None = None,
        hosts: list[str] | None = None,
    ) -> list[StoredDocument]:
        where, parameters = self._filters(sources, hosts, alias="d")
        rows = self.connection.execute(
            f"SELECT d.* FROM documents d JOIN sources s ON s.configured_source=d.configured_source "
            f"WHERE s.active=1 {where}",
            parameters,
        ).fetchall()
        return [self._document(row) for row in rows]

    @staticmethod
    def _filters(sources: list[str] | None, hosts: list[str] | None, alias: str) -> tuple[str, list[str]]:
        clauses: list[str] = []
        parameters: list[str] = []
        if sources:
            clauses.append(f"{alias}.configured_source IN ({','.join('?' for _ in sources)})")
            parameters.extend(sources)
        if hosts:
            clauses.append(
                f"({alias}.source_host IN ({','.join('?' for _ in hosts)}) OR "
                f"{alias}.canonical_host IN ({','.join('?' for _ in hosts)}))"
            )
            parameters.extend(hosts)
            parameters.extend(hosts)
        return (" AND " + " AND ".join(clauses) if clauses else "", parameters)

    @staticmethod
    def _source(row: sqlite3.Row) -> SourceState:
        return SourceState(
            configured_source=row["configured_source"],
            resolved_source=row["resolved_source"],
            active=bool(row["active"]),
            etag=row["etag"],
            last_modified=row["last_modified"],
            body_hash=row["body_hash"],
            raw_body=row["raw_body"],
            parser_fingerprint=row["parser_fingerprint"],
            embedding_fingerprint=row["embedding_fingerprint"],
            checked_at=row["checked_at"],
            indexed_at=row["indexed_at"],
            stale_at=row["stale_at"],
            last_error=row["last_error"],
            doc_count=row["doc_count"],
        )

    @staticmethod
    def _document(row: sqlite3.Row) -> StoredDocument:
        return StoredDocument(
            id=row["id"],
            configured_source=row["configured_source"],
            resolved_source=row["resolved_source"],
            source_host=row["source_host"],
            canonical_url=row["canonical_url"],
            canonical_host=row["canonical_host"],
            title=row["title"],
            description=row["description"],
            heading_path=row["heading_path"],
            content=row["content"],
            content_hash=row["content_hash"],
            embedding=np.frombuffer(row["embedding"], dtype=np.float32, count=row["embedding_dim"]).copy(),
        )
