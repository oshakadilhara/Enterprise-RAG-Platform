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
    vector_score: float = 0.0
    bm25_score: float = 0.0
    hybrid_score: float = 0.0
    rerank_score: float = 0.0
    upload_date: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievalContext:
    query: str
    expanded_queries: list[str]
    results: list[SearchResult]
    context_text: str
    total_retrieval_ms: int
    stages: dict[str, int] = field(default_factory=dict)
