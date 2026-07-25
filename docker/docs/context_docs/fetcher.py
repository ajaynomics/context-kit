from __future__ import annotations

import httpx

from .models import FetchResponse, SourceState


class SourceFetcher:
    def __init__(self, timeout_seconds: float = 30, max_bytes: int = 20_000_000):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "context-kit-docs/1.0"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(self, source_url: str, state: SourceState | None = None) -> FetchResponse:
        headers: dict[str, str] = {}
        if state and state.etag:
            headers["If-None-Match"] = state.etag
        if state and state.last_modified:
            headers["If-Modified-Since"] = state.last_modified
        async with self._client.stream("GET", source_url, headers=headers) as response:
            if response.status_code == 304:
                return FetchResponse(
                    status=304,
                    requested_url=source_url,
                    resolved_url=str(response.url),
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                )
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self.max_bytes:
                    raise RuntimeError(f"source exceeds {self.max_bytes} byte limit")
                chunks.append(chunk)
            body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            return FetchResponse(
                status=response.status_code,
                requested_url=source_url,
                resolved_url=str(response.url),
                body=body,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )
