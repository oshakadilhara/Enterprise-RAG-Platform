"""Document ingestion pipeline orchestrator."""

import json
import uuid
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.telemetry import DOCUMENT_PROCESSING
from app.domain.interfaces.embedding import EmbeddingProvider
from app.services.ingestion.chunker import get_chunker
from app.services.ingestion.extractors import get_extractor
from app.services.search.opensearch_service import OpenSearchService
from app.services.vector.qdrant_service import QdrantService

logger = get_logger(__name__)

ALLOWED_TYPES = {"pdf", "docx", "txt", "csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class IngestionPipeline:
    def __init__(
        self,
        settings: Settings,
        embedding: EmbeddingProvider,
        qdrant: QdrantService,
        opensearch: OpenSearchService,
    ):
        self._settings = settings
        self._embedding = embedding
        self._qdrant = qdrant
        self._opensearch = opensearch

    def validate(self, file_name: str, file_size: int) -> str:
        ext = file_name.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_TYPES:
            raise ValueError(f"Unsupported file type: {ext}. Allowed: {ALLOWED_TYPES}")
        if file_size > MAX_FILE_SIZE:
            raise ValueError(f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)}MB")
        return ext

    async def process(
        self,
        file_content: bytes,
        file_name: str,
        document_id: uuid.UUID,
        workspace_id: uuid.UUID,
        chunking_strategy: str | None = None,
    ) -> dict:
        file_type = self.validate(file_name, len(file_content))
        strategy = chunking_strategy or self._settings.chunking_strategy

        try:
            # Extract
            extractor = get_extractor(file_type)
            extracted = await extractor.extract(file_content, file_name)

            # Clean
            cleaned_pages = []
            for page in extracted.pages:
                cleaned = self._clean_text(page.content)
                if cleaned:
                    cleaned_pages.append((cleaned, page.page_number))

            # Chunk
            chunker = get_chunker(
                strategy,
                self._settings.chunk_size,
                self._settings.chunk_overlap,
            )
            all_chunks = []
            global_index = 0
            for text, page_num in cleaned_pages:
                chunks = chunker.chunk(text, page_num, start_index=global_index)
                all_chunks.extend(chunks)
                global_index += len(chunks)

            if not all_chunks:
                raise ValueError("No text content extracted from document")

            # Embed
            texts = [c.content for c in all_chunks]
            embeddings = await self._embedding.embed_batch(texts)

            upload_date = datetime.now(UTC).isoformat()
            vector_points = []
            search_docs = []

            for chunk, embedding in zip(all_chunks, embeddings):
                chunk_id = str(uuid.uuid4())
                payload = {
                    "chunk_id": chunk_id,
                    "document_id": str(document_id),
                    "workspace_id": str(workspace_id),
                    "file_name": file_name,
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "upload_date": upload_date,
                }
                vector_points.append({
                    "id": chunk_id,
                    "vector": embedding,
                    "payload": payload,
                })
                search_docs.append(payload)

            # Store vectors
            await self._qdrant.upsert_vectors(
                workspace_id, vector_points, self._embedding.dimension
            )

            # Index in OpenSearch
            await self._opensearch.index_documents(workspace_id, search_docs)

            DOCUMENT_PROCESSING.labels(status="success", file_type=file_type).inc()
            logger.info(
                "document_processed",
                document_id=str(document_id),
                chunks=len(all_chunks),
                file_type=file_type,
            )

            return {
                "chunk_count": len(all_chunks),
                "page_count": extracted.metadata.get("page_count"),
                "chunks": [
                    {
                        "chunk_id": p["id"],
                        "chunk_index": c.chunk_index,
                        "page_number": c.page_number,
                        "content": c.content,
                        "token_count": c.token_count,
                        "vector_id": p["id"],
                        "opensearch_id": p["payload"]["chunk_id"],
                    }
                    for c, p in zip(all_chunks, vector_points)
                ],
                "metadata": extracted.metadata,
            }

        except Exception as e:
            DOCUMENT_PROCESSING.labels(status="failed", file_type=file_type).inc()
            logger.error("document_processing_failed", error=str(e), document_id=str(document_id))
            raise

    @staticmethod
    def _clean_text(text: str) -> str:
        import re
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^\S\n]+", " ", text)
        text = text.strip()
        return text
