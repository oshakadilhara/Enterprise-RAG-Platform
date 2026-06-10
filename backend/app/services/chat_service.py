"""Chat service with streaming and citations."""

import json
import time
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import CurrentUser
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.telemetry import QUERY_COUNT, TOKEN_USAGE
from app.domain.interfaces.llm import LLMProvider
from app.models.conversation import Conversation, Message
from app.models.usage import UsageMetric
from app.repositories.conversation_repository import ConversationRepository, MessageRepository
from app.repositories.workspace_repository import WorkspaceMemberRepository
from app.schemas.chat import ChatRequest, ChatResponse, Citation, MessageResponse
from app.services.retrieval.pipeline import RetrievalPipeline


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        retrieval: RetrievalPipeline,
        llm: LLMProvider,
    ):
        self._session = session
        self._retrieval = retrieval
        self._llm = llm
        self._conv_repo = ConversationRepository(session)
        self._msg_repo = MessageRepository(session)
        self._member_repo = WorkspaceMemberRepository(session)
        self._settings = get_settings()

    async def chat(
        self,
        request: ChatRequest,
        current_user: CurrentUser,
    ) -> ChatResponse:
        start = time.perf_counter()
        conversation = await self._get_or_create_conversation(request, current_user)
        await self._check_workspace_access(request.workspace_id, current_user.id)

        # Save user message
        user_msg = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="user",
            content=request.message,
        )
        await self._msg_repo.create(user_msg)

        # Retrieve context
        context = await self._retrieval.retrieve(request.message, request.workspace_id)

        # Build messages with history
        history = await self._get_chat_history(conversation.id)
        messages = self._retrieval.build_llm_messages(request.message, context, history)

        # Generate response
        response = await self._llm.generate(messages)
        latency_ms = int((time.perf_counter() - start) * 1000)

        citations = self._build_citations(context.results)
        assistant_msg = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="assistant",
            content=response.content,
            citations_json=json.dumps([c.model_dump(mode="json") for c in citations]),
            token_count=response.tokens_output,
            latency_ms=latency_ms,
            model=response.model,
        )
        await self._msg_repo.create(assistant_msg)

        await self._track_usage(current_user, request.workspace_id, response, latency_ms, context.total_retrieval_ms)
        QUERY_COUNT.labels(workspace_id=str(request.workspace_id), status="success").inc()

        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_msg.id,
            content=response.content,
            citations=citations,
            model=response.model,
            latency_ms=latency_ms,
            token_count=response.tokens_output,
        )

    async def chat_stream(
        self,
        request: ChatRequest,
        current_user: CurrentUser,
    ) -> AsyncGenerator[str, None]:
        conversation = await self._get_or_create_conversation(request, current_user)
        await self._check_workspace_access(request.workspace_id, current_user.id)

        user_msg = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="user",
            content=request.message,
        )
        await self._msg_repo.create(user_msg)

        context = await self._retrieval.retrieve(request.message, request.workspace_id)
        history = await self._get_chat_history(conversation.id)
        messages = self._retrieval.build_llm_messages(request.message, context, history)
        citations = self._build_citations(context.results)

        # Send metadata first
        yield f"data: {json.dumps({'type': 'metadata', 'conversation_id': str(conversation.id), 'citations': [c.model_dump(mode='json') for c in citations]})}\n\n"

        full_content = ""
        async for chunk in self._llm.generate_stream(messages):
            full_content += chunk
            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

        assistant_msg = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="assistant",
            content=full_content,
            citations_json=json.dumps([c.model_dump(mode="json") for c in citations]),
            model=self._llm.model_name,
        )
        await self._msg_repo.create(assistant_msg)
        yield f"data: {json.dumps({'type': 'done', 'message_id': str(assistant_msg.id)})}\n\n"

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

    async def _get_chat_history(self, conversation_id: UUID) -> list[dict[str, str]]:
        messages = await self._msg_repo.list_by_conversation(conversation_id)
        return [{"role": m.role, "content": m.content} for m in messages[-10:]]

    def _build_citations(self, results) -> list[Citation]:
        return [
            Citation(
                document_id=r.document_id,
                file_name=r.file_name,
                page_number=r.page_number,
                chunk_index=r.chunk_index,
                content_snippet=r.content[:200],
                relevance_score=r.rerank_score or r.hybrid_score,
            )
            for r in results
        ]

    async def _track_usage(
        self, user, workspace_id, response, latency_ms, retrieval_ms
    ) -> None:
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
