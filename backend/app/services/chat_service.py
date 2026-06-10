"""Chat service with streaming, citations, caching, budgets and explainability.

Production hardening (docs/COST_OPTIMIZATION.md, docs/EXPLAINABLE_AI.md):
- Per-user / per-org rate limits and daily token budgets (Redis)
- Semantic answer cache: identical questions in a workspace skip the LLM
- Abstention: refuses to generate when retrieval confidence is too low
- Citation score breakdown (vector / bm25 / rerank / match type)
- Retrieval trace persisted with every assistant message for auditability
- Output token cap and token-budgeted history
"""

import json
import time
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import CurrentUser
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.core.telemetry import QUERY_COUNT, TOKEN_USAGE
from app.domain.entities.retrieval import RetrievalContext, SearchResult
from app.domain.interfaces.llm import LLMProvider
from app.models.conversation import Conversation, Message
from app.models.usage import UsageMetric
from app.repositories.conversation_repository import ConversationRepository, MessageRepository
from app.repositories.workspace_repository import WorkspaceMemberRepository
from app.schemas.chat import ChatRequest, ChatResponse, Citation
from app.services.cache_service import CacheService
from app.services.retrieval.pipeline import RetrievalPipeline

logger = get_logger(__name__)


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        retrieval: RetrievalPipeline,
        llm: LLMProvider,
        cache: CacheService | None = None,
    ):
        self._session = session
        self._retrieval = retrieval
        self._llm = llm
        self._cache = cache or CacheService()
        self._conv_repo = ConversationRepository(session)
        self._msg_repo = MessageRepository(session)
        self._member_repo = WorkspaceMemberRepository(session)
        self._settings = get_settings()

    # ── Non-streaming chat ───────────────────────────────────

    async def chat(self, request: ChatRequest, current_user: CurrentUser) -> ChatResponse:
        start = time.perf_counter()
        await self._enforce_limits(current_user)
        conversation = await self._get_or_create_conversation(request, current_user)
        await self._check_workspace_access(request.workspace_id, current_user.id)

        user_msg = await self._save_user_message(conversation.id, request.message)

        # Semantic answer cache: identical question in this workspace → no LLM call
        cached = await self._cache.get_answer(request.workspace_id, request.message)
        if cached:
            assistant_msg = await self._save_assistant_message(
                conversation_id=conversation.id,
                content=cached["content"],
                citations_json=json.dumps(cached["citations"]),
                trace_json=json.dumps({"cache_hit": True}),
                model=cached.get("model", self._llm.model_name),
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
            return ChatResponse(
                conversation_id=conversation.id,
                message_id=assistant_msg.id,
                content=cached["content"],
                citations=[Citation(**c) for c in cached["citations"]],
                model=cached.get("model", self._llm.model_name),
                latency_ms=assistant_msg.latency_ms or 0,
                confidence=cached.get("confidence", 0.0),
                cached=True,
            )

        context = await self._retrieval.retrieve(request.message, request.workspace_id)
        citations = self._build_citations(context.results)
        trace_json = json.dumps(context.to_trace())

        # Abstention: don't pay for generation that would hallucinate
        if self._should_abstain(context):
            latency_ms = int((time.perf_counter() - start) * 1000)
            assistant_msg = await self._save_assistant_message(
                conversation_id=conversation.id,
                content=self._retrieval.ABSTAIN_MESSAGE,
                citations_json=json.dumps([c.model_dump(mode="json") for c in citations]),
                trace_json=trace_json,
                model="abstention",
                latency_ms=latency_ms,
            )
            QUERY_COUNT.labels(workspace_id=str(request.workspace_id), status="abstained").inc()
            return ChatResponse(
                conversation_id=conversation.id,
                message_id=assistant_msg.id,
                content=self._retrieval.ABSTAIN_MESSAGE,
                citations=citations,
                model="abstention",
                latency_ms=latency_ms,
                confidence=context.top_score,
                abstained=True,
            )

        history = await self._get_chat_history(conversation.id, exclude_id=user_msg.id)
        messages = self._retrieval.build_llm_messages(request.message, context, history)

        response = await self._llm.generate(
            messages, max_tokens=self._settings.answer_max_tokens
        )
        latency_ms = int((time.perf_counter() - start) * 1000)

        assistant_msg = await self._save_assistant_message(
            conversation_id=conversation.id,
            content=response.content,
            citations_json=json.dumps([c.model_dump(mode="json") for c in citations]),
            trace_json=trace_json,
            model=response.model,
            latency_ms=latency_ms,
            token_count=response.tokens_output,
        )

        await self._track_usage(
            current_user, request.workspace_id, response, latency_ms, context.total_retrieval_ms
        )
        await self._cache.record_token_usage(
            current_user.organization_id,
            (response.tokens_input or 0) + (response.tokens_output or 0),
        )
        await self._cache.set_answer(
            request.workspace_id,
            request.message,
            {
                "content": response.content,
                "citations": [c.model_dump(mode="json") for c in citations],
                "model": response.model,
                "confidence": context.top_score,
            },
        )
        QUERY_COUNT.labels(workspace_id=str(request.workspace_id), status="success").inc()

        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_msg.id,
            content=response.content,
            citations=citations,
            model=response.model,
            latency_ms=latency_ms,
            token_count=response.tokens_output,
            confidence=context.top_score,
        )

    # ── Streaming chat ───────────────────────────────────────

    async def chat_stream(
        self, request: ChatRequest, current_user: CurrentUser
    ) -> AsyncGenerator[dict, None]:
        """Yields SSE-ready event dicts: metadata → content* → done."""
        await self._enforce_limits(current_user)
        conversation = await self._get_or_create_conversation(request, current_user)
        await self._check_workspace_access(request.workspace_id, current_user.id)

        user_msg = await self._save_user_message(conversation.id, request.message)

        cached = await self._cache.get_answer(request.workspace_id, request.message)
        if cached:
            yield self._metadata_event(conversation.id, cached["citations"],
                                       confidence=cached.get("confidence", 0.0), cached=True)
            yield {"type": "content", "content": cached["content"]}
            assistant_msg = await self._save_assistant_message(
                conversation_id=conversation.id,
                content=cached["content"],
                citations_json=json.dumps(cached["citations"]),
                trace_json=json.dumps({"cache_hit": True}),
                model=cached.get("model", self._llm.model_name),
            )
            yield {"type": "done", "message_id": str(assistant_msg.id)}
            return

        context = await self._retrieval.retrieve(request.message, request.workspace_id)
        citations = self._build_citations(context.results)
        citations_payload = [c.model_dump(mode="json") for c in citations]
        trace_json = json.dumps(context.to_trace())

        yield self._metadata_event(conversation.id, citations_payload,
                                   confidence=context.top_score,
                                   abstained=self._should_abstain(context))

        if self._should_abstain(context):
            yield {"type": "content", "content": self._retrieval.ABSTAIN_MESSAGE}
            assistant_msg = await self._save_assistant_message(
                conversation_id=conversation.id,
                content=self._retrieval.ABSTAIN_MESSAGE,
                citations_json=json.dumps(citations_payload),
                trace_json=trace_json,
                model="abstention",
            )
            QUERY_COUNT.labels(workspace_id=str(request.workspace_id), status="abstained").inc()
            yield {"type": "done", "message_id": str(assistant_msg.id)}
            return

        history = await self._get_chat_history(conversation.id, exclude_id=user_msg.id)
        messages = self._retrieval.build_llm_messages(request.message, context, history)

        full_content = ""
        async for chunk in self._llm.generate_stream(
            messages, max_tokens=self._settings.answer_max_tokens
        ):
            full_content += chunk
            yield {"type": "content", "content": chunk}

        assistant_msg = await self._save_assistant_message(
            conversation_id=conversation.id,
            content=full_content,
            citations_json=json.dumps(citations_payload),
            trace_json=trace_json,
            model=self._llm.model_name,
        )
        await self._cache.set_answer(
            request.workspace_id,
            request.message,
            {
                "content": full_content,
                "citations": citations_payload,
                "model": self._llm.model_name,
                "confidence": context.top_score,
            },
        )
        QUERY_COUNT.labels(workspace_id=str(request.workspace_id), status="success").inc()
        yield {"type": "done", "message_id": str(assistant_msg.id)}

    # ── Internals ────────────────────────────────────────────

    async def _enforce_limits(self, current_user: CurrentUser) -> None:
        await self._cache.check_rate_limits(current_user.id, current_user.organization_id)
        await self._cache.check_token_budget(current_user.organization_id)

    def _should_abstain(self, context: RetrievalContext) -> bool:
        return self._settings.abstain_on_low_confidence and not context.confident

    @staticmethod
    def _metadata_event(
        conversation_id: UUID,
        citations: list[dict],
        confidence: float,
        abstained: bool = False,
        cached: bool = False,
    ) -> dict:
        return {
            "type": "metadata",
            "conversation_id": str(conversation_id),
            "citations": citations,
            "confidence": round(confidence, 4),
            "abstained": abstained,
            "cached": cached,
        }

    async def _save_user_message(self, conversation_id: UUID, content: str) -> Message:
        msg = Message(id=uuid4(), conversation_id=conversation_id, role="user", content=content)
        return await self._msg_repo.create(msg)

    async def _save_assistant_message(
        self,
        conversation_id: UUID,
        content: str,
        citations_json: str,
        trace_json: str,
        model: str,
        latency_ms: int | None = None,
        token_count: int | None = None,
    ) -> Message:
        msg = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            citations_json=citations_json,
            retrieval_trace_json=trace_json,
            model=model,
            latency_ms=latency_ms,
            token_count=token_count,
        )
        return await self._msg_repo.create(msg)

    async def _get_or_create_conversation(
        self, request: ChatRequest, current_user: CurrentUser
    ) -> Conversation:
        if request.conversation_id:
            conv = await self._conv_repo.get_by_id(request.conversation_id)
            if not conv or conv.user_id != current_user.id:
                raise NotFoundError("Conversation", str(request.conversation_id))
            return conv

        conv = Conversation(
            id=uuid4(),
            user_id=current_user.id,
            workspace_id=request.workspace_id,
            title=request.message[:100],
        )
        return await self._conv_repo.create(conv)

    async def _check_workspace_access(self, workspace_id: UUID, user_id: UUID) -> None:
        membership = await self._member_repo.get_membership(workspace_id, user_id)
        if not membership:
            raise ForbiddenError("No access to this workspace")

    async def _get_chat_history(
        self, conversation_id: UUID, exclude_id: UUID | None = None
    ) -> list[dict[str, str]]:
        """Recent history; trimming to token budget happens in the pipeline."""
        messages = await self._msg_repo.list_by_conversation(conversation_id)
        return [
            {"role": m.role, "content": m.content}
            for m in messages[-10:]
            if m.id != exclude_id
        ]

    def _build_citations(self, results: list[SearchResult]) -> list[Citation]:
        return [
            Citation(
                document_id=r.document_id,
                file_name=r.file_name,
                page_number=r.page_number,
                chunk_index=r.chunk_index,
                content_snippet=r.content[:200],
                relevance_score=r.rerank_score or r.hybrid_score,
                vector_score=round(r.vector_score, 4),
                bm25_score=round(r.bm25_score, 4),
                rerank_score=round(r.rerank_score, 4),
                match_type=r.match_type,
            )
            for r in results
        ]

    async def _track_usage(self, user, workspace_id, response, latency_ms, retrieval_ms) -> None:
        TOKEN_USAGE.labels(provider=self._settings.llm_provider, type="input").inc(
            response.tokens_input or 0
        )
        TOKEN_USAGE.labels(provider=self._settings.llm_provider, type="output").inc(
            response.tokens_output or 0
        )
        metric = UsageMetric(
            id=uuid4(),
            organization_id=user.organization_id,
            user_id=user.id,
            workspace_id=workspace_id,
            metric_type="query",
            tokens_input=response.tokens_input,
            tokens_output=response.tokens_output,
            latency_ms=latency_ms,
            retrieval_ms=retrieval_ms,
            provider=self._settings.llm_provider,
            model=response.model,
        )
        self._session.add(metric)
