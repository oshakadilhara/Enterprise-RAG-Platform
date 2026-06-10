"""Retrieval domain entities."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class SearchResult:
    chunk_id: str
    document_id: UUID
    workspace_id: UUID
    content: str
    file_name: str
    page_number: int | None
    chunk_index: int
    vector_score: float = 0.0       # normalized within result set
    bm25_score: float = 0.0         # normalized within result set
    hybrid_score: float = 0.0       # weighted fusion of the above
    rerank_score: float = 0.0       # cross-encoder, sigmoid-normalized 0-1
    raw_vector_score: float = 0.0   # absolute cosine similarity (confidence gate)
    upload_date: str | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def match_type(self) -> str:
        """Why this chunk surfaced — for explainability (docs/EXPLAINABLE_AI.md)."""
        has_semantic = self.vector_score > 0.5
        has_keyword = self.bm25_score > 0.5
        if has_semantic and has_keyword:
            return "both"
        if has_keyword:
            return "keyword"
        return "semantic"


@dataclass
class RetrievalContext:
    query: str
    expanded_queries: list[str]
    results: list[SearchResult]
    context_text: str
    total_retrieval_ms: int
    stages: dict[str, int] = field(default_factory=dict)
    confident: bool = True          # top rerank score >= threshold
    top_score: float = 0.0          # best rerank score in results
    expansion_skipped: bool = False  # confidence gate skipped LLM expansion

    def to_trace(self) -> dict:
        """Audit trace persisted with each message (docs/EXPLAINABLE_AI.md)."""
        return {
            "expanded_queries": self.expanded_queries,
            "expansion_skipped": self.expansion_skipped,
            "stage_latencies_ms": self.stages,
            "total_retrieval_ms": self.total_retrieval_ms,
            "confident": self.confident,
            "top_score": round(self.top_score, 4),
            "chunk_scores": [
                {
                    "chunk_id": r.chunk_id,
                    "document_id": str(r.document_id),
                    "vector_score": round(r.vector_score, 4),
                    "bm25_score": round(r.bm25_score, 4),
                    "rerank_score": round(r.rerank_score, 4),
                    "match_type": r.match_type,
                }
                for r in self.results
            ],
        }
