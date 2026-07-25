from __future__ import annotations

import asyncio
import hashlib

import numpy as np


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.fingerprint = f"sentence-transformers:{model_name}"
        self._model = None
        self._lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return self._model is not None

    async def ensure_ready(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._load)

    def _load(self):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.model_name, device="cpu")

    async def encode_documents(self, texts: list[str]) -> np.ndarray:
        await self.ensure_ready()
        return await asyncio.to_thread(self._encode, texts)

    async def encode_query(self, text: str) -> np.ndarray:
        vectors = await self.encode_documents([text])
        return vectors[0]

    def _encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self._model.encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                normalize_embeddings=True,
                convert_to_numpy=True,
            ),
            dtype=np.float32,
        )


class LexicalFallbackEmbedder:
    """Deterministic fallback used only when a model cannot be loaded."""

    fingerprint = "lexical-fallback-v1"
    ready = True

    async def ensure_ready(self) -> None:
        return None

    async def encode_documents(self, texts: list[str]) -> np.ndarray:
        return np.asarray([self._encode(text) for text in texts], dtype=np.float32)

    async def encode_query(self, text: str) -> np.ndarray:
        return np.asarray(self._encode(text), dtype=np.float32)

    @staticmethod
    def _encode(text: str, dimensions: int = 384) -> np.ndarray:
        vector = np.zeros(dimensions, dtype=np.float32)
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % dimensions] += 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector
