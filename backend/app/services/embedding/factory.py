"""Embedding provider factory."""

from app.core.config import Settings
from app.domain.interfaces.embedding import EmbeddingProvider
from app.services.embedding.bge import BGEEmbeddingProvider
from app.services.embedding.gemini import GeminiEmbeddingProvider
from app.services.embedding.openai import OpenAIEmbeddingProvider
from app.services.embedding.sentence_transformers import SentenceTransformersProvider


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    providers = {
        "openai": OpenAIEmbeddingProvider,
        "gemini": GeminiEmbeddingProvider,
        "bge": BGEEmbeddingProvider,
        "sentence_transformers": SentenceTransformersProvider,
    }
    provider_class = providers.get(settings.embedding_provider)
    if not provider_class:
        raise ValueError(f"Unknown embedding provider: {settings.embedding_provider}")
    return provider_class(settings)
