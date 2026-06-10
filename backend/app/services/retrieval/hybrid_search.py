"""Hybrid search combining vector similarity and BM25."""

import time
from uuid import UUID

from app.core.config import Settings
from app.core.telemetry import RETRIEVAL_LATENCY
from app.domain.entities.retrieval import SearchResult
from app.domain.interfaces.embedding import EmbeddingProvider
from app.services.search.opensearch_service import OpenSearchService
from app.services.vector.qdrant_service import QdrantService


class HybridSearchService:
    def __init__(
        self,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        qdrant: QdrantService,
        opensearch: OpenSearchService,
    ):
        self._settings = settings
        self._embedding = embedding_provider
        self._qdrant = qdrant
        self._opensearch = opensearch

    async def search(
        self,
        query: str,
        workspace_id: UUID,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        top_k = top_k or self._settings.hybrid_top_k
        vector_weight = self._settings.vector_search_weight
        bm25_weight = self._settings.bm25_search_weight

        # Vector search
        start = time.perf_counter()
        query_vector = await self._embedding.embed_text(query)
        vector_results = await self._qdrant.search(
            workspace_id=workspace_id,
            query_vector=query_vector,
            top_k=top_k,
            filters=filters,
        )
        RETRIEVAL_LATENCY.labels(stage="vector_search").observe(time.perf_counter() - start)

        # BM25 search
        start = time.perf_counter()
        bm25_results = await self._opensearch.search(
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            filters=filters,
        )
        RETRIEVAL_LATENCY.labels(stage="bm25_search").observe(time.perf_counter() - start)

        # Normalize scores
        vector_scores = self._normalize_scores(
            {r["id"]: r["score"] for r in vector_results}
        )
        bm25_scores = self._normalize_scores(
            {r["id"]: r["score"] for r in bm25_results}
        )

        # Merge results
        merged: dict[str, SearchResult] = {}

        for result in vector_results:
            chunk_id = result["id"]
            payload = result["payload"]
            merged[chunk_id] = SearchResult(
                chunk_id=chunk_id,
                document_id=UUID(payload["document_id"]),
                workspace_id=workspace_id,
                content=payload.get("content", ""),
                file_name=payload.get("file_name", ""),
                page_number=payload.get("page_number"),
                chunk_index=payload.get("chunk_index", 0),
                vector_score=vector_scores.get(chunk_id, 0.0),
                upload_date=payload.get("upload_date"),
                metadata=payload,
            )

        for result in bm25_results:
            chunk_id = result["id"]
            source = result["source"]
            if chunk_id in merged:
                merged[chunk_id].bm25_score = bm25_scores.get(chunk_id, 0.0)
            else:
                merged[chunk_id] = SearchResult(
                    chunk_id=chunk_id,
                    document_id=UUID(source["document_id"]),
                    workspace_id=workspace_id,
                    content=source.get("content", ""),
                    file_name=source.get("file_name", ""),
                    page_number=source.get("page_number"),
                    chunk_index=source.get("chunk_index", 0),
                    bm25_score=bm25_scores.get(chunk_id, 0.0),
                    upload_date=source.get("upload_date"),
                    metadata=source,
                )

        # Compute hybrid scores
        for result in merged.values():
            result.hybrid_score = (
                vector_weight * result.vector_score + bm25_weight * result.bm25_score
            )

        ranked = sorted(merged.values(), key=lambda r: r.hybrid_score, reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        max_score = max(scores.values())
        if max_score == 0:
            return {k: 0.0 for k in scores}
        return {k: v / max_score for k, v in scores.items()}
