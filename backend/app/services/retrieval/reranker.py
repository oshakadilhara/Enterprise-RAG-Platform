"""Reranking service using BGE or Cross-Encoder models."""

import asyncio
import time

from sentence_transformers import CrossEncoder

from app.core.config import Settings
from app.core.telemetry import RETRIEVAL_LATENCY
from app.domain.entities.retrieval import SearchResult
from app.domain.interfaces.reranker import RankedResult, Reranker


class BGEReranker(Reranker):
    def __init__(self, settings: Settings):
        self._model = CrossEncoder(settings.reranker_model)

    async def rerank(
        self,
        query: str,
        documents: list[RankedResult],
        top_k: int = 5,
    ) -> list[RankedResult]:
        if not documents:
            return []

        pairs = [(query, doc.content) for doc in documents]
        scores = await asyncio.to_thread(self._model.predict, pairs)

        for doc, score in zip(documents, scores):
            doc.score = float(score)

        return sorted(documents, key=lambda d: d.score, reverse=True)[:top_k]


class CrossEncoderReranker(Reranker):
    def __init__(self, settings: Settings):
        model_name = settings.reranker_model or "cross-encoder/ms-marco-MiniLM-L-6-v2"
        self._model = CrossEncoder(model_name)

    async def rerank(
        self,
        query: str,
        documents: list[RankedResult],
        top_k: int = 5,
    ) -> list[RankedResult]:
        if not documents:
            return []
        pairs = [(query, doc.content) for doc in documents]
        scores = await asyncio.to_thread(self._model.predict, pairs)
        for doc, score in zip(documents, scores):
            doc.score = float(score)
        return sorted(documents, key=lambda d: d.score, reverse=True)[:top_k]


class RerankerService:
    def __init__(self, settings: Settings):
        rerankers = {
            "bge": BGEReranker,
            "cross_encoder": CrossEncoderReranker,
        }
        reranker_class = rerankers.get(settings.reranker_provider, BGEReranker)
        self._reranker = reranker_class(settings)
        self._top_k = settings.rerank_top_k

    async def rerank(
        self,
        query: str,
        results: list[SearchResult],
    ) -> list[SearchResult]:
        start = time.perf_counter()
        ranked_docs = [
            RankedResult(
                id=r.chunk_id,
                content=r.content,
                score=r.hybrid_score,
                metadata=r.metadata,
            )
            for r in results
        ]
        reranked = await self._reranker.rerank(query, ranked_docs, top_k=self._top_k)
        RETRIEVAL_LATENCY.labels(stage="reranking").observe(time.perf_counter() - start)

        score_map = {doc.id: doc.score for doc in reranked}
        result_map = {r.chunk_id: r for r in results}

        final = []
        for doc in reranked:
            if doc.id in result_map:
                result = result_map[doc.id]
                result.rerank_score = score_map[doc.id]
                final.append(result)
        return final
