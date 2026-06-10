"""Document management API."""

from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile

from app.core.dependencies import CurrentUserDep, DbSession
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.document import DocumentResponse, DocumentUploadResponse
from app.services.document_service import DocumentService

router = APIRouter()


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    current_user: CurrentUserDep,
    db: DbSession,
    workspace_id: UUID = Query(...),
    file: UploadFile = File(...),
):
    current_user.require_permission("document:create")
    content = await file.read()
    service = DocumentService(db)
    return await service.upload(content, file.filename or "unknown", workspace_id, current_user)


@router.get("", response_model=PaginatedResponse[DocumentResponse])
async def list_documents(
    current_user: CurrentUserDep,
    db: DbSession,
    workspace_id: UUID = Query(...),
    status: str | None = None,
    file_type: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    current_user.require_permission("document:read")
    service = DocumentService(db)
    docs, total = await service.list_documents(
        workspace_id, current_user, status, file_type, search, page, page_size
    )
    return PaginatedResponse(
        items=docs,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: CurrentUserDep,
    db: DbSession,
):
    service = DocumentService(db)
    return await service.get_document(document_id, current_user)


@router.delete("/{document_id}", response_model=MessageResponse)
async def delete_document(
    document_id: UUID,
    current_user: CurrentUserDep,
    db: DbSession,
):
    service = DocumentService(db)
    await service.delete_document(document_id, current_user)
    return MessageResponse(message="Document deleted")
