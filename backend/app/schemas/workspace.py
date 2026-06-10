"""Workspace schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BaseSchema


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    chunking_strategy: str = "recursive"


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    chunking_strategy: str | None = None


class WorkspaceResponse(BaseSchema):
    id: UUID
    name: str
    description: str | None
    organization_id: UUID
    created_by: UUID
    chunking_strategy: str
    created_at: datetime
    updated_at: datetime
    member_count: int = 0
    document_count: int = 0


class WorkspaceMemberInvite(BaseModel):
    email: str
    role: str = "member"


class WorkspaceMemberResponse(BaseSchema):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    role: str
    joined_at: datetime
