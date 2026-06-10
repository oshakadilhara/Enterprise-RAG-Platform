"""Qdrant vector store service."""

from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class QdrantService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        self._prefix = settings.qdrant_collection_prefix

    def _collection_name(self, workspace_id: UUID) -> str:
        return f"{self._prefix}{str(workspace_id).replace('-', '_')}"

    async def ensure_collection(self, workspace_id: UUID, dimension: int) -> str:
        name = self._collection_name(workspace_id)
        collections = await self._client.get_collections()
        existing = {c.name for c in collections.collections}

        if name not in existing:
            await self._client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=dimension,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            await self._client.create_payload_index(
                collection_name=name,
                field_name="document_id",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            await self._client.create_payload_index(
                collection_name=name,
                field_name="workspace_id",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            logger.info("created_qdrant_collection", collection=name)

        return name

    async def upsert_vectors(
        self,
        workspace_id: UUID,
        points: list[dict],
        dimension: int,
    ) -> None:
        collection = await self.ensure_collection(workspace_id, dimension)
        qdrant_points = [
            qmodels.PointStruct(
                id=point["id"],
                vector=point["vector"],
                payload=point["payload"],
            )
            for point in points
        ]
        await self._client.upsert(collection_name=collection, points=qdrant_points)

    async def search(
        self,
        workspace_id: UUID,
        query_vector: list[float],
        top_k: int = 50,
        filters: dict | None = None,
        score_threshold: float | None = None,
    ) -> list[dict]:
        collection = self._collection_name(workspace_id)
        query_filter = None
        if filters:
            conditions = [
                qmodels.FieldCondition(
                    key=key,
                    match=qmodels.MatchValue(value=value),
                )
                for key, value in filters.items()
            ]
            query_filter = qmodels.Filter(must=conditions)

        results = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )

        return [
            {
                "id": str(hit.id),
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in results
        ]

    async def delete_by_document(self, workspace_id: UUID, document_id: str) -> None:
        collection = self._collection_name(workspace_id)
        await self._client.delete(
            collection_name=collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )

    async def delete_collection(self, workspace_id: UUID) -> None:
        collection = self._collection_name(workspace_id)
        await self._client.delete_collection(collection_name=collection)
