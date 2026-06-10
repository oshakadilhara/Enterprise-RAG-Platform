"""Sentence Transformers embedding provider."""

import asyncio
import time

from sentence_transformers import SentenceTransformer

from app.core.config import Settings
from app.core.telemetry import EMBEDDING_LATENCY
from app.domain.interfaces.embedding import EmbeddingProvider


class SentenceTransformersProvider(EmbeddingProvider):
    def __init__(self, settings: Settings):
        self._model_name = settings.embedding_model or "all-MiniLM-L6-v2"
        self._model = SentenceTransformer(self._model_name)
        self._dimension = self._model.get_sentence_embedding_dimension()

    async def embed_text(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        start = time.perf_counter()
        embeddings = await asyncio.to_thread(
            self._model.encode,
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        EMBEDDING_LATENCY.labels(provider="sentence_transformers").observe(
            time.perf_counter() - start
        )
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name
