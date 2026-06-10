"""Dependency container for service instantiation."""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.cache_service import CacheService
from app.services.chat_service import ChatService
from app.services.embedding.factory import create_embedding_provider
from app.services.llm.factory import create_llm_provider, create_utility_llm_provider
from app.services.retrieval.hybrid_search import HybridSearchService
from app.services.retrieval.pipeline import RetrievalPipeline
from app.services.retrieval.reranker import RerankerService
from app.services.search.opensearch_service import OpenSearchService
from app.services.vector.qdrant_service import QdrantService


@lru_cache
def _get_settings():
    return get_settings()


@lru_cache
def get_cache_service() -> CacheService:
    return CacheService(_get_settings())


@lru_cache
def get_retrieval_pipeline() -> RetrievalPipeline:
    """Cached: the reranker holds a loaded cross-encoder model and must not
    be re-instantiated per request."""
    settings = _get_settings()
    embedding = create_embedding_provider(settings)
    llm = create_llm_provider(settings)
    utility_llm = create_utility_llm_provider(settings)
    qdrant = QdrantService(settings)
    opensearch = OpenSearchService(settings)
    cache = get_cache_service()
    hybrid = HybridSearchService(settings, embedding, qdrant, opensearch, cache=cache)
    reranker = RerankerService(settings)
    return RetrievalPipeline(settings, hybrid, reranker, llm, embedding, utility_llm=utility_llm)


def get_chat_service(db: AsyncSession) -> ChatService:
    settings = _get_settings()
    llm = create_llm_provider(settings)
    retrieval = get_retrieval_pipeline()
    return ChatService(db, retrieval, llm, cache=get_cache_service())
