"""Document schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BaseSchema


class DocumentResponse(BaseSchema):
    id: UUID
    workspace_id: UUID
    owner_id: UUID
    file_name: str
    file_type: str
    file_size: int
    status: str
    page_count: int | None
    chunk_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    id: UUID
    file_name: str
    status: str
    message: str


class DocumentListParams(BaseModel):
    workspace_id: UUID
    status: str | None = None
    file_type: str | None = None
    search: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
