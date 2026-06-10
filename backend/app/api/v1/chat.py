"""Chat API with streaming support."""

import json
from uuid import UUID

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.dependencies import CurrentUserDep, DbSession
from app.core.exceptions import NotFoundError
from app.repositories.conversation_repository import ConversationRepository, MessageRepository
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationResponse,
    MessageResponse,
)
from app.schemas.common import PaginatedResponse
from app.services.chat_service import ChatService
from app.services.container import get_chat_service

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: CurrentUserDep,
    db: DbSession,
):
    current_user.require_permission("chat:create")
    service = get_chat_service(db)
    return await service.chat(request, current_user)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: CurrentUserDep,
    db: DbSession,
):
    current_user.require_permission("chat:create")
    service = get_chat_service(db)

    async def event_generator():
        async for event in service.chat_stream(request, current_user):
            yield {"event": event["type"], "data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    request: ConversationCreate,
    current_user: CurrentUserDep,
    db: DbSession,
):
    from uuid import uuid4
    from app.models.conversation import Conversation

    repo = ConversationRepository(db)
    conv = Conversation(
        id=uuid4(),
        user_id=current_user.id,
        workspace_id=request.workspace_id,
        title=request.title,
    )
    conv = await repo.create(conv)
    return ConversationResponse.model_validate(conv)


@router.get("/conversations", response_model=PaginatedResponse[ConversationResponse])
async def list_conversations(
    current_user: CurrentUserDep,
    db: DbSession,
    workspace_id: UUID | None = None,
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    repo = ConversationRepository(db)
    convs, total = await repo.list_by_user(
        current_user.id, workspace_id, query, page, page_size
    )
    items = [
        ConversationResponse(
            id=c.id,
            user_id=c.user_id,
            workspace_id=c.workspace_id,
            title=c.title,
            is_archived=c.is_archived,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=len(c.messages),
        )
        for c in convs
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conversation_id: UUID,
    current_user: CurrentUserDep,
    db: DbSession,
):
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    conv = await conv_repo.get_by_id(conversation_id)
    if not conv or conv.user_id != current_user.id:
        raise NotFoundError("Conversation", str(conversation_id))

    messages = await msg_repo.list_by_conversation(conversation_id)
    result = []
    for m in messages:
        citations = json.loads(m.citations_json) if m.citations_json else None
        trace = json.loads(m.retrieval_trace_json) if m.retrieval_trace_json else None
        result.append(MessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            citations=citations,
            retrieval_trace=trace,
            model=m.model,
            latency_ms=m.latency_ms,
            created_at=m.created_at,
        ))
    return result
