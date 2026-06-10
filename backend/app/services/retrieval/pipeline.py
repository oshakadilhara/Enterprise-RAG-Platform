"""Full retrieval pipeline: gated query expansion → hybrid search → rerank → context.

Production hardening applied here (see docs/COST_OPTIMIZATION.md, docs/EXPLAINABLE_AI.md):
- Confidence-gated query expansion: a cheap pre-search with the original query
  skips the LLM expansion call entirely when retrieval is already confident.
- Query expansion runs on the utility model (e.g. gpt-4o-mini), not the main model.
- Abstention signal: when the best rerank score is below threshold the caller
  can refuse to generate instead of hallucinating.
- Token-budgeted chat history instead of fixed message count.
"""

import asyncio
import time
from uuid import UUID

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.telemetry import RETRIEVAL_LATENCY
from app.domain.entities.retrieval import RetrievalContext, SearchResult
from app.domain.interfaces.embedding import EmbeddingProvider
from app.domain.interfaces.llm import LLMProvider
from app.services.retrieval.hybrid_search import HybridSearchService
from app.services.retrieval.reranker import RerankerService

logger = get_logger(__name__)


def estimate_tokens(text: str) -> int:
    """Fast heuristic (~4 chars/token for English). Good enough for budgeting;
    exact counts would need a tokenizer round-trip per message."""
    return max(1, len(text) // 4)


class RetrievalPipeline:
    SYSTEM_PROMPT = """You are an enterprise knowledge assistant. Answer questions based ONLY on the provided context.
Always cite your sources using [Source: filename, Page X] format.
If the context doesn't contain enough information, say so clearly.
Be concise, accurate, and professional."""

    ABSTAIN_MESSAGE = (
        "I could not find sufficiently relevant information in this workspace's "
        "documents to answer your question confidently. Try rephrasing the question, "
        "or check that the relevant documents have been uploaded and processed."
    )

    def __init__(
        self,
        settings: Settings,
        hybrid_search: HybridSearchService,
        reranker: RerankerService,
        llm: LLMProvider,
        embedding: EmbeddingProvider,
        utility_llm: LLMProvider | None = None,
    ):
        self._settings = settings
        self._hybrid_search = hybrid_search
        self._reranker = reranker
        self._llm = llm
        # Cheap model for internal calls; falls back to the main model
        self._utility_llm = utility_llm or llm
        self._embedding = embedding

    async def retrieve(
        self,
        query: str,
        workspace_id: UUID,
        filters: dict | None = None,
    ) -> RetrievalContext:
        total_start = time.perf_counter()
        stages: dict[str, int] = {}

        # Initial hybrid search with the original query (always needed)
        start = time.perf_counter()
        base_results = await self._hybrid_search.search(query, workspace_id, filters=filters)
        stages["initial_search"] = int((time.perf_counter() - start) * 1000)

        # Confidence gate: only pay for LLM expansion when the original
        # query retrieved weakly (Cost Tier 1, ~50% of expansion calls saved)
        top_raw = max((r.raw_vector_score for r in base_results), default=0.0)
        expansion_skipped = top_raw >= self._settings.expansion_confidence_threshold
        expanded = [query]
        all_results = list(base_results)

        if not expansion_skipped:
            start = time.perf_counter()
            alternatives = await self._expand_query(query)
            stages["query_expansion"] = int((time.perf_counter() - start) * 1000)

            if alternatives:
                expanded = [query] + alternatives
                start = time.perf_counter()
                alt_result_lists = await asyncio.gather(
                    *(
                        self._hybrid_search.search(q, workspace_id, filters=filters)
                        for q in alternatives
                    ),
                    return_exceptions=True,
                )
                for res in alt_result_lists:
                    if isinstance(res, Exception):
                        logger.warning("expanded_search_failed", error=str(res))
                    else:
                        all_results.extend(res)
                stages["expanded_search"] = int((time.perf_counter() - start) * 1000)

        # Deduplicate by chunk_id, keep highest hybrid score
        seen: dict[str, SearchResult] = {}
        for r in all_results:
            if r.chunk_id not in seen or r.hybrid_score > seen[r.chunk_id].hybrid_score:
                seen[r.chunk_id] = r
        deduped = sorted(seen.values(), key=lambda r: r.hybrid_score, reverse=True)

        # Reranking
        start = time.perf_counter()
        reranked = await self._reranker.rerank(query, deduped[: self._settings.hybrid_top_k])
        stages["reranking"] = int((time.perf_counter() - start) * 1000)

        # Confidence / abstention signal (XAI Tier 1)
        top_score = max((r.rerank_score for r in reranked), default=0.0)
        confident = top_score >= self._settings.retrieval_confidence_threshold

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
            confident=confident,
            top_score=top_score,
            expansion_skipped=expansion_skipped,
        )

    async def _expand_query(self, query: str) -> list[str]:
        """Generate query variations for better recall. Uses the utility model."""
        try:
            response = await self._utility_llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "Generate 2 alternative phrasings of the user query for document search. Return one per line, no numbering.",
                    },
                    {"role": "user", "content": query},
                ],
                temperature=0.3,
                max_tokens=200,
            )
            alternatives = [
                line.strip() for line in response.content.strip().split("\n") if line.strip()
            ]
            return alternatives[:2]
        except Exception as e:
            logger.warning("query_expansion_failed", error=str(e))
            return []

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
        """Prompt-cache friendly ordering: stable system prompt first, then
        history (a growing prefix across turns), volatile context+question last."""
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        if chat_history:
            messages.extend(self._trim_history(chat_history))
        messages.append({
            "role": "user",
            "content": f"Context:\n{context.context_text}\n\nQuestion: {query}",
        })
        return messages

    def _trim_history(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        """Keep the most recent messages within the token budget (Cost Tier 1).

        Walks backwards from the newest message so a single long answer
        cannot crowd out the user's latest question."""
        budget = self._settings.history_max_tokens
        kept: list[dict[str, str]] = []
        used = 0
        for msg in reversed(history):
            cost = estimate_tokens(msg["content"])
            if used + cost > budget and kept:
                break
            kept.append(msg)
            used += cost
        return list(reversed(kept))
