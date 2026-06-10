"""Celery background tasks."""

import asyncio
import uuid
from uuid import UUID

from app.workers.celery_app import celery_app


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, document_id: str):
    return _run_async(_process_document(document_id))


async def _process_document(document_id: str):
    from app.core.config import get_settings
    from app.core.database import async_session_factory
    from app.models.document import Document, DocumentChunk
    from app.repositories.document_repository import DocumentChunkRepository, DocumentRepository
    from app.services.embedding.factory import create_embedding_provider
    from app.services.ingestion.pipeline import IngestionPipeline
    from app.services.search.opensearch_service import OpenSearchService
    from app.services.vector.qdrant_service import QdrantService

    settings = get_settings()
    async with async_session_factory() as session:
        doc_repo = DocumentRepository(session)
        chunk_repo = DocumentChunkRepository(session)

        doc = await doc_repo.get_by_id(UUID(document_id))
        if not doc:
            return {"error": "Document not found"}

        doc.status = "processing"
        await doc_repo.update(doc)
        await session.commit()

        try:
            with open(doc.storage_path, "rb") as f:
                content = f.read()

            embedding = create_embedding_provider(settings)
            pipeline = IngestionPipeline(
                settings, embedding,
                QdrantService(settings),
                OpenSearchService(settings),
            )
            result = await pipeline.process(
                content, doc.file_name, doc.id, doc.workspace_id
            )

            chunks = [
                DocumentChunk(
                    id=UUID(c["chunk_id"]) if _is_uuid(c["chunk_id"]) else uuid.uuid4(),
                    document_id=doc.id,
                    workspace_id=doc.workspace_id,
                    chunk_index=c["chunk_index"],
                    content=c["content"],
                    page_number=c.get("page_number"),
                    token_count=c["token_count"],
                    vector_id=c["vector_id"],
                    opensearch_id=c["opensearch_id"],
                )
                for c in result["chunks"]
            ]
            await chunk_repo.bulk_create(chunks)

            doc.status = "completed"
            doc.chunk_count = result["chunk_count"]
            doc.page_count = result.get("page_count")
            await doc_repo.update(doc)
            await session.commit()

            return {"status": "completed", "chunks": result["chunk_count"]}

        except Exception as e:
            doc.status = "failed"
            doc.error_message = str(e)
            await doc_repo.update(doc)
            await session.commit()
            raise


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


@celery_app.task(bind=True)
def run_evaluation_task(self, evaluation_id: str):
    return _run_async(_run_evaluation(evaluation_id))


async def _run_evaluation(evaluation_id: str):
    from datetime import UTC, datetime

    from app.core.database import async_session_factory
    from app.models.evaluation import EvaluationRun
    from app.services.evaluation.evaluator import RAGEvaluator

    async with async_session_factory() as session:
        eval_run = await session.get(EvaluationRun, UUID(evaluation_id))
        if not eval_run:
            return {"error": "Evaluation not found"}

        eval_run.status = "running"
        await session.commit()

        try:
            evaluator = RAGEvaluator()
            results = await evaluator.run(eval_run.workspace_id, eval_run.framework)

            eval_run.precision_at_k = results.get("precision_at_k")
            eval_run.recall_at_k = results.get("recall_at_k")
            eval_run.mrr = results.get("mrr")
            eval_run.ndcg = results.get("ndcg")
            eval_run.faithfulness = results.get("faithfulness")
            eval_run.answer_relevancy = results.get("answer_relevancy")
            eval_run.context_precision = results.get("context_precision")
            eval_run.status = "completed"
            eval_run.completed_at = datetime.now(UTC)
            await session.commit()
            return results
        except Exception as e:
            eval_run.status = "failed"
            await session.commit()
            raise
