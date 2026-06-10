"""Chat and conversation schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BaseSchema


class Citation(BaseModel):
    document_id: UUID
    file_name: str
    page_number: int | None
    chunk_index: int
    content_snippet: str
    relevance_score: float


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    workspace_id: UUID
    conversation_id: UUID | None = None
    stream: bool = True


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    content: str
    citations: list[Citation]
    model: str
    latency_ms: int
    token_count: int | None = None


class ConversationCreate(BaseModel):
    workspace_id: UUID
    title: str = "New Conversation"


class ConversationResponse(BaseSchema):
    id: UUID
    user_id: UUID
    workspace_id: UUID
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageResponse(BaseSchema):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    citations: list[Citation] | None = None
    model: str | None
    latency_ms: int | None
    created_at: datetime


class ConversationSearchParams(BaseModel):
    workspace_id: UUID | None = None
    query: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
