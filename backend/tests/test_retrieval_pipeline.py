"""Tests for retrieval pipeline hardening: gated expansion, abstention, trace."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.entities.retrieval import RetrievalContext, SearchResult
from app.services.retrieval.pipeline import RetrievalPipeline, estimate_tokens


def make_result(raw_vector: float = 0.9, rerank: float = 0.8, **kwargs) -> SearchResult:
    defaults = dict(
        chunk_id=str(uuid4()),
        document_id=uuid4(),
        workspace_id=uuid4(),
        content="some chunk content",
        file_name="doc.pdf",
        page_number=1,
        chunk_index=0,
        vector_score=0.9,
        bm25_score=0.3,
        hybrid_score=0.7,
        rerank_score=rerank,
        raw_vector_score=raw_vector,
    )
    defaults.update(kwargs)
    return SearchResult(**defaults)


def make_settings(**overrides):
    settings = MagicMock()
    settings.hybrid_top_k = 50
    settings.expansion_confidence_threshold = 0.7
    settings.retrieval_confidence_threshold = 0.3
    settings.abstain_on_low_confidence = True
    settings.history_max_tokens = 100
    for k, v in overrides.items():
        setattr(settings, k, v)
    return settings


def make_pipeline(settings, results):
    hybrid = MagicMock()
    hybrid.search = AsyncMock(return_value=results)
    reranker = MagicMock()
    reranker.rerank = AsyncMock(side_effect=lambda q, r: r[:5])
    llm = MagicMock()
    llm.generate = AsyncMock()
    utility = MagicMock()
    utility.generate = AsyncMock(
        return_value=MagicMock(content="alt one\nalt two")
    )
    pipeline = RetrievalPipeline(settings, hybrid, reranker, llm, MagicMock(), utility_llm=utility)
    return pipeline, hybrid, utility


@pytest.mark.asyncio
async def test_expansion_skipped_when_confident():
    settings = make_settings()
    pipeline, hybrid, utility = make_pipeline(settings, [make_result(raw_vector=0.92)])

    ctx = await pipeline.retrieve("query", uuid4())

    assert ctx.expansion_skipped is True
    utility.generate.assert_not_called()
    assert hybrid.search.call_count == 1  # only the original query


@pytest.mark.asyncio
async def test_expansion_runs_when_weak():
    settings = make_settings()
    pipeline, hybrid, utility = make_pipeline(settings, [make_result(raw_vector=0.4)])

    ctx = await pipeline.retrieve("query", uuid4())

    assert ctx.expansion_skipped is False
    utility.generate.assert_called_once()
    assert hybrid.search.call_count == 3  # original + 2 alternatives


@pytest.mark.asyncio
async def test_abstention_signal_on_low_rerank_score():
    settings = make_settings()
    pipeline, _, _ = make_pipeline(settings, [make_result(raw_vector=0.9, rerank=0.1)])

    ctx = await pipeline.retrieve("query", uuid4())

    assert ctx.confident is False
    assert ctx.top_score == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_trace_contains_score_breakdown():
    settings = make_settings()
    pipeline, _, _ = make_pipeline(settings, [make_result(raw_vector=0.9)])

    ctx = await pipeline.retrieve("query", uuid4())
    trace = ctx.to_trace()

    assert trace["confident"] is True
    assert trace["chunk_scores"]
    first = trace["chunk_scores"][0]
    assert {"vector_score", "bm25_score", "rerank_score", "match_type"} <= set(first)


def test_history_trim_respects_token_budget():
    settings = make_settings(history_max_tokens=20)
    pipeline, _, _ = make_pipeline(settings, [])

    history = [
        {"role": "user", "content": "x" * 400},       # ~100 tokens, dropped
        {"role": "assistant", "content": "y" * 40},   # ~10 tokens, kept
        {"role": "user", "content": "z" * 40},        # ~10 tokens, kept
    ]
    trimmed = pipeline._trim_history(history)

    assert len(trimmed) == 2
    assert trimmed[0]["content"].startswith("y")
    assert trimmed[-1]["content"].startswith("z")


def test_match_type_classification():
    assert make_result(vector_score=0.9, bm25_score=0.9).match_type == "both"
    assert make_result(vector_score=0.9, bm25_score=0.1).match_type == "semantic"
    assert make_result(vector_score=0.1, bm25_score=0.9).match_type == "keyword"


def test_estimate_tokens():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100
