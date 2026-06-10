"""Analytics and evaluation API."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.dependencies import CurrentUserDep, DbSession
from app.models.evaluation import EvaluationRun
from app.models.usage import UsageMetric
from app.schemas.analytics import (
    AnalyticsResponse,
    DailyMetric,
    EvaluationRequest,
    EvaluationResponse,
    UsageSummary,
)
from app.workers.tasks import run_evaluation_task

router = APIRouter()


@router.get("/usage", response_model=AnalyticsResponse)
async def get_usage_analytics(
    current_user: CurrentUserDep,
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
):
    current_user.require_permission("analytics:read")
    since = datetime.now(UTC) - timedelta(days=days)

    result = await db.execute(
        select(
            func.count(UsageMetric.id),
            func.sum(UsageMetric.tokens_input + UsageMetric.tokens_output),
            func.sum(UsageMetric.cost_usd),
            func.avg(UsageMetric.latency_ms),
            func.avg(UsageMetric.retrieval_ms),
        ).where(
            UsageMetric.organization_id == current_user.organization_id,
            UsageMetric.created_at >= since,
        )
    )
    row = result.one()

    daily_result = await db.execute(
        select(
            func.date(UsageMetric.created_at).label("date"),
            func.count(UsageMetric.id).label("queries"),
            func.sum(UsageMetric.tokens_input + UsageMetric.tokens_output).label("tokens"),
            func.sum(UsageMetric.cost_usd).label("cost"),
            func.avg(UsageMetric.latency_ms).label("latency"),
        )
        .where(
            UsageMetric.organization_id == current_user.organization_id,
            UsageMetric.created_at >= since,
        )
        .group_by(func.date(UsageMetric.created_at))
        .order_by(func.date(UsageMetric.created_at))
    )

    daily_metrics = [
        DailyMetric(
            date=r.date,
            queries=r.queries or 0,
            tokens=int(r.tokens or 0),
            cost_usd=float(r.cost or 0),
            avg_latency_ms=float(r.latency or 0),
        )
        for r in daily_result.all()
    ]

    return AnalyticsResponse(
        summary=UsageSummary(
            total_queries=row[0] or 0,
            total_tokens=int(row[1] or 0),
            total_cost_usd=float(row[2] or 0),
            avg_latency_ms=float(row[3] or 0),
            avg_retrieval_ms=float(row[4] or 0),
        ),
        daily_metrics=daily_metrics,
        top_workspaces=[],
        provider_breakdown={},
    )


@router.post("/evaluation", response_model=EvaluationResponse, status_code=201)
async def run_evaluation(
    request: EvaluationRequest,
    current_user: CurrentUserDep,
    db: DbSession,
):
    current_user.require_permission("evaluation:run")
    eval_run = EvaluationRun(
        id=uuid4(),
        workspace_id=request.workspace_id,
        created_by=current_user.id,
        framework=request.framework,
        status="pending",
    )
    db.add(eval_run)
    await db.flush()

    run_evaluation_task.delay(str(eval_run.id))

    return EvaluationResponse(
        id=eval_run.id,
        workspace_id=eval_run.workspace_id,
        framework=eval_run.framework,
        status=eval_run.status,
        precision_at_k=None,
        recall_at_k=None,
        mrr=None,
        ndcg=None,
        faithfulness=None,
        answer_relevancy=None,
        context_precision=None,
        created_at=eval_run.created_at,
        completed_at=None,
    )


@router.get("/evaluation/{evaluation_id}", response_model=EvaluationResponse)
async def get_evaluation(
    evaluation_id: UUID,
    current_user: CurrentUserDep,
    db: DbSession,
):
    eval_run = await db.get(EvaluationRun, evaluation_id)
    if not eval_run:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Evaluation", str(evaluation_id))

    return EvaluationResponse(
        id=eval_run.id,
        workspace_id=eval_run.workspace_id,
        framework=eval_run.framework,
        status=eval_run.status,
        precision_at_k=eval_run.precision_at_k,
        recall_at_k=eval_run.recall_at_k,
        mrr=eval_run.mrr,
        ndcg=eval_run.ndcg,
        faithfulness=eval_run.faithfulness,
        answer_relevancy=eval_run.answer_relevancy,
        context_precision=eval_run.context_precision,
        created_at=eval_run.created_at,
        completed_at=eval_run.completed_at,
    )
