from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from context_docs.models import FetchResponse


class FakeEmbedder:
    fingerprint = "fake-embedder-v1"
    ready = True

    async def ensure_ready(self) -> None:
        return None

    async def encode_documents(self, texts: list[str]) -> np.ndarray:
        return np.asarray([self._vector(text) for text in texts], dtype=np.float32)

    async def encode_query(self, text: str) -> np.ndarray:
        return np.asarray(self._vector(text), dtype=np.float32)

    @staticmethod
    def _vector(text: str) -> list[float]:
        lower = text.lower()
        return [
            float("api" in lower or "identifier" in lower),
            float("persistence" in lower or "checkpoint" in lower),
            float("background" in lower or "asynchronous" in lower),
            0.25 + (int(hashlib.sha256(text.encode()).hexdigest()[:2], 16) / 1024),
        ]


@dataclass
class FakeFetch:
    status: int
    body: str = ""
    final_url: str | None = None
    etag: str | None = None
    last_modified: str | None = None


class FakeFetcher:
    def __init__(self, responses: list[FakeFetch]):
        self.responses = list(responses)
        self.calls = 0

    async def fetch(self, source_url: str, state=None) -> FetchResponse:
        self.calls += 1
        response = self.responses.pop(0)
        return FetchResponse(
            status=response.status,
            requested_url=source_url,
            resolved_url=response.final_url or source_url,
            body=response.body,
            etag=response.etag,
            last_modified=response.last_modified,
        )
