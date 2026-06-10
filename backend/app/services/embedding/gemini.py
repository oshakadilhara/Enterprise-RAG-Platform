"""Google Gemini embedding provider."""

import time

import google.generativeai as genai

from app.core.config import Settings
from app.core.telemetry import EMBEDDING_LATENCY
from app.domain.interfaces.embedding import EmbeddingProvider


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        genai.configure(api_key=settings.google_api_key)
        self._model = settings.embedding_model or "models/text-embedding-004"
        self._dimension = settings.embedding_dimension

    async def embed_text(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        start = time.perf_counter()
        result = genai.embed_content(
            model=self._model,
            content=texts,
            task_type="retrieval_document",
        )
        EMBEDDING_LATENCY.labels(provider="gemini").observe(time.perf_counter() - start)
        embeddings = result["embedding"]
        if texts and not isinstance(embeddings[0], list):
            return [embeddings]
        return embeddings

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model
