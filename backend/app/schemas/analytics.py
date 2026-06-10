"""Analytics and monitoring schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class UsageSummary(BaseModel):
    total_queries: int
    total_tokens: int
    total_cost_usd: float
    avg_latency_ms: float
    avg_retrieval_ms: float


class DailyMetric(BaseModel):
    date: date
    queries: int
    tokens: int
    cost_usd: float
    avg_latency_ms: float


class AnalyticsResponse(BaseModel):
    summary: UsageSummary
    daily_metrics: list[DailyMetric]
    top_workspaces: list[dict]
    provider_breakdown: dict[str, int]


class EvaluationRequest(BaseModel):
    workspace_id: UUID
    framework: str = "ragas"  # ragas | deepeval
    dataset_path: str | None = None


class EvaluationResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    framework: str
    status: str
    precision_at_k: float | None
    recall_at_k: float | None
    mrr: float | None
    ndcg: float | None
    faithfulness: float | None
    answer_relevancy: float | None
    context_precision: float | None
    created_at: datetime
    completed_at: datetime | None
