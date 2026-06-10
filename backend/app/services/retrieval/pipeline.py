"""Full retrieval pipeline: query expansion → hybrid search → rerank → context."""

import time
from uuid import UUID

from app.core.config import Settings
from app.core.telemetry import RETRIEVAL_LATENCY
from app.domain.entities.retrieval import RetrievalContext, SearchResult
from app.domain.interfaces.embedding import EmbeddingProvider
from app.domain.interfaces.llm import LLMProvider
from app.services.retrieval.hybrid_search import HybridSearchService
from app.services.retrieval.reranker import RerankerService


class RetrievalPipeline:
    SYSTEM_PROMPT = """You are an enterprise knowledge assistant. Answer questions based ONLY on the provided context.
Always cite your sources using [Source: filename, Page X] format.
If the context doesn't contain enough information, say so clearly.
Be concise, accurate, and professional."""

    def __init__(
        self,
        settings: Settings,
        hybrid_search: HybridSearchService,
        reranker: RerankerService,
        llm: LLMProvider,
        embedding: EmbeddingProvider,
    ):
        self._settings = settings
        self._hybrid_search = hybrid_search
        self._reranker = reranker
        self._llm = llm
        self._embedding = embedding

    async def retrieve(
        self,
        query: str,
        workspace_id: UUID,
        filters: dict | None = None,
    ) -> RetrievalContext:
        total_start = time.perf_counter()
        stages: dict[str, int] = {}

        # Query expansion
        start = time.perf_counter()
        expanded = await self._expand_query(query)
        stages["query_expansion"] = int((time.perf_counter() - start) * 1000)

        # Hybrid search
        start = time.perf_counter()
        all_results: list[SearchResult] = []
        for q in expanded:
            results = await self._hybrid_search.search(q, workspace_id, filters=filters)
            all_results.extend(results)
        # Deduplicate by chunk_id, keep highest score
        seen: dict[str, SearchResult] = {}
        for r in all_results:
            if r.chunk_id not in seen or r.hybrid_score > seen[r.chunk_id].hybrid_score:
                seen[r.chunk_id] = r
        deduped = sorted(seen.values(), key=lambda r: r.hybrid_score, reverse=True)
        stages["hybrid_search"] = int((time.perf_counter() - start) * 1000)

        # Reranking
        start = time.perf_counter()
        reranked = await self._reranker.rerank(query, deduped[:self._settings.hybrid_top_k])
        stages["reranking"] = int((time.perf_counter() - start) * 1000)

        # Context building
        context_text = self._build_context(reranked)
        total_ms = int((time.perf_counter() - total_start) * 1000)
        RETRIEVAL_LATENCY.labels(stage="total").observe(time.perf_counter() - total_start)

        return RetrievalContext(
            query=query,
            expanded_queries=expanded,
            results=reranked,
            context_text=context_text,
            total_retrieval_ms=total_ms,
            stages=stages,
        )

    async def _expand_query(self, query: str) -> list[str]:
        """Generate query variations for better recall."""
        try:
            response = await self._llm.generate(
                messages=[
                    {"role": "system", "content": "Generate 2 alternative phrasings of the user query for document search. Return one per line, no numbering."},
                    {"role": "user", "content": query},
                ],
                temperature=0.3,
                max_tokens=200,
            )
            alternatives = [
                line.strip() for line in response.content.strip().split("\n") if line.strip()
            ]
            return [query] + alternatives[:2]
        except Exception:
            return [query]

    def _build_context(self, results: list[SearchResult]) -> str:
        if not results:
            return "No relevant context found."
        parts = []
        for i, result in enumerate(results, 1):
            page_info = f", Page {result.page_number}" if result.page_number else ""
            parts.append(
                f"[Context {i}] Source: {result.file_name}{page_info}\n{result.content}"
            )
        return "\n\n".join(parts)

    def build_llm_messages(
        self,
        query: str,
        context: RetrievalContext,
        chat_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        if chat_history:
            messages.extend(chat_history[-6:])
        messages.append({
            "role": "user",
            "content": f"Context:\n{context.context_text}\n\nQuestion: {query}",
        })
        return messages
