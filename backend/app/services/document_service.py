"""Document management service."""

import os
import uuid
from uuid import UUID, uuid4

import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import CurrentUser
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.models.document import Document, DocumentChunk
from app.repositories.document_repository import DocumentChunkRepository, DocumentRepository
from app.repositories.workspace_repository import WorkspaceMemberRepository
from app.schemas.document import DocumentResponse, DocumentUploadResponse
from app.services.cache_service import CacheService
from app.services.search.opensearch_service import OpenSearchService
from app.services.vector.qdrant_service import QdrantService
from app.workers.tasks import process_document_task

logger = get_logger(__name__)


class DocumentService:
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv"}

    def __init__(self, session: AsyncSession):
        self._session = session
        self._doc_repo = DocumentRepository(session)
        self._chunk_repo = DocumentChunkRepository(session)
        self._member_repo = WorkspaceMemberRepository(session)
        self._settings = get_settings()
        self._upload_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(self._upload_dir, exist_ok=True)

    async def upload(
        self,
        file_content: bytes,
        file_name: str,
        workspace_id: UUID,
        current_user: CurrentUser,
    ) -> DocumentUploadResponse:
        await self._check_access(workspace_id, current_user.id)

        ext = os.path.splitext(file_name)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        file_type = ext.lstrip(".")
        doc_id = uuid4()
        storage_name = f"{workspace_id}/{doc_id}{ext}"
        storage_path = os.path.join(self._upload_dir, storage_name)
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)

        async with aiofiles.open(storage_path, "wb") as f:
            await f.write(file_content)

        document = Document(
            id=doc_id,
            workspace_id=workspace_id,
            owner_id=current_user.id,
            file_name=file_name,
            file_type=file_type,
            file_size=len(file_content),
            storage_path=storage_path,
            status="pending",
        )
        await self._doc_repo.create(document)

        process_document_task.delay(str(doc_id))

        return DocumentUploadResponse(
            id=doc_id,
            file_name=file_name,
            status="pending",
            message="Document uploaded and queued for processing",
        )

    async def list_documents(
        self,
        workspace_id: UUID,
        current_user: CurrentUser,
        status: str | None = None,
        file_type: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DocumentResponse], int]:
        await self._check_access(workspace_id, current_user.id)
        docs, total = await self._doc_repo.list_by_workspace(
            workspace_id, status, file_type, search, page, page_size
        )
        return [DocumentResponse.model_validate(d) for d in docs], total

    async def get_document(
        self, document_id: UUID, current_user: CurrentUser
    ) -> DocumentResponse:
        doc = await self._doc_repo.get_by_id(document_id)
        if not doc:
            raise NotFoundError("Document", str(document_id))
        await self._check_access(doc.workspace_id, current_user.id)
        return DocumentResponse.model_validate(doc)

    async def delete_document(
        self, document_id: UUID, current_user: CurrentUser
    ) -> None:
        doc = await self._doc_repo.get_by_id(document_id)
        if not doc:
            raise NotFoundError("Document", str(document_id))
        await self._check_access(doc.workspace_id, current_user.id)
        current_user.require_permission("document:delete")

        workspace_id = doc.workspace_id

        # Remove from search indexes first; a chunk that survives deletion
        # would keep leaking into retrieval results
        try:
            qdrant = QdrantService(self._settings)
            await qdrant.delete_by_document(workspace_id, str(document_id))
        except Exception as e:
            logger.error("qdrant_delete_failed", document_id=str(document_id), error=str(e))
        try:
            opensearch = OpenSearchService(self._settings)
            await opensearch.delete_by_document(workspace_id, str(document_id))
        except Exception as e:
            logger.error("opensearch_delete_failed", document_id=str(document_id), error=str(e))

        if os.path.exists(doc.storage_path):
            os.remove(doc.storage_path)
        await self._doc_repo.delete(doc)

        # Cached answers may cite the deleted document
        await CacheService(self._settings).invalidate_workspace(workspace_id)

    async def _check_access(self, workspace_id: UUID, user_id: UUID) -> None:
        membership = await self._member_repo.get_membership(workspace_id, user_id)
        if not membership:
            raise ForbiddenError("No access to this workspace")
