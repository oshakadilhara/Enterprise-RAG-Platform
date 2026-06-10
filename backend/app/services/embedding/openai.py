"""OpenAI embedding provider."""

import time

from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.telemetry import EMBEDDING_LATENCY
from app.domain.interfaces.embedding import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.embedding_model
        self._dimension = settings.embedding_dimension

    async def embed_text(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        start = time.perf_counter()
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        EMBEDDING_LATENCY.labels(provider="openai").observe(time.perf_counter() - start)
        return [item.embedding for item in response.data]

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model
