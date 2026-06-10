"""Dependency container for service instantiation."""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.chat_service import ChatService
from app.services.embedding.factory import create_embedding_provider
from app.services.llm.factory import create_llm_provider
from app.services.retrieval.hybrid_search import HybridSearchService
from app.services.retrieval.pipeline import RetrievalPipeline
from app.services.retrieval.reranker import RerankerService
from app.services.search.opensearch_service import OpenSearchService
from app.services.vector.qdrant_service import QdrantService


@lru_cache
def _get_settings():
    return get_settings()


def get_retrieval_pipeline() -> RetrievalPipeline:
    settings = _get_settings()
    embedding = create_embedding_provider(settings)
    llm = create_llm_provider(settings)
    qdrant = QdrantService(settings)
    opensearch = OpenSearchService(settings)
    hybrid = HybridSearchService(settings, embedding, qdrant, opensearch)
    reranker = RerankerService(settings)
    return RetrievalPipeline(settings, hybrid, reranker, llm, embedding)


def get_chat_service(db: AsyncSession) -> ChatService:
    settings = _get_settings()
    llm = create_llm_provider(settings)
    retrieval = get_retrieval_pipeline()
    return ChatService(db, retrieval, llm)
