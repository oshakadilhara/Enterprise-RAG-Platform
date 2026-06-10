"""Embedding provider factory.

Provider modules are imported lazily so a deployment only needs the SDK of
the provider it actually configures (e.g. no torch install for OpenAI-only).
"""

from app.core.config import Settings
from app.domain.interfaces.embedding import EmbeddingProvider


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.embedding_provider

    if provider == "openai":
        from app.services.embedding.openai import OpenAIEmbeddingProvider
        return OpenAIEmbeddingProvider(settings)
    if provider == "gemini":
        from app.services.embedding.gemini import GeminiEmbeddingProvider
        return GeminiEmbeddingProvider(settings)
    if provider == "bge":
        from app.services.embedding.bge import BGEEmbeddingProvider
        return BGEEmbeddingProvider(settings)
    if provider == "sentence_transformers":
        from app.services.embedding.sentence_transformers import SentenceTransformersProvider
        return SentenceTransformersProvider(settings)

    raise ValueError(f"Unknown embedding provider: {provider}")
