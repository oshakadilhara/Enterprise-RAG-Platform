"""OpenSearch BM25 full-text search service."""

from uuid import UUID

from opensearchpy import AsyncOpenSearch

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class OpenSearchService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = AsyncOpenSearch(
            hosts=[{"host": settings.opensearch_host, "port": settings.opensearch_port}],
            http_auth=(settings.opensearch_user, settings.opensearch_password),
            use_ssl=settings.opensearch_use_ssl,
            verify_certs=settings.opensearch_use_ssl,
        )
        self._prefix = settings.opensearch_index_prefix

    def _index_name(self, workspace_id: UUID) -> str:
        return f"{self._prefix}{str(workspace_id).replace('-', '_')}"

    async def ensure_index(self, workspace_id: UUID) -> str:
        index = self._index_name(workspace_id)
        exists = await self._client.indices.exists(index=index)
        if not exists:
            await self._client.indices.create(
                index=index,
                body={
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "analysis": {
                            "analyzer": {
                                "rag_analyzer": {
                                    "type": "standard",
                                    "stopwords": "_english_",
                                }
                            }
                        },
                    },
                    "mappings": {
                        "properties": {
                            "chunk_id": {"type": "keyword"},
                            "document_id": {"type": "keyword"},
                            "workspace_id": {"type": "keyword"},
                            "file_name": {"type": "keyword"},
                            "content": {"type": "text", "analyzer": "rag_analyzer"},
                            "page_number": {"type": "integer"},
                            "chunk_index": {"type": "integer"},
                            "upload_date": {"type": "date"},
                        }
                    },
                },
            )
            logger.info("created_opensearch_index", index=index)
        return index

    async def index_documents(self, workspace_id: UUID, documents: list[dict]) -> None:
        index = await self.ensure_index(workspace_id)
        for doc in documents:
            await self._client.index(
                index=index,
                id=doc["chunk_id"],
                body=doc,
                refresh=True,
            )

    async def search(
        self,
        workspace_id: UUID,
        query: str,
        top_k: int = 50,
        filters: dict | None = None,
    ) -> list[dict]:
        index = self._index_name(workspace_id)
        must = [{"match": {"content": {"query": query, "operator": "or"}}}]
        filter_clauses = []

        if filters:
            for key, value in filters.items():
                filter_clauses.append({"term": {key: value}})

        body = {
            "query": {
                "bool": {
                    "must": must,
                    "filter": filter_clauses,
                }
            },
            "size": top_k,
            "highlight": {
                "fields": {"content": {"fragment_size": 150, "number_of_fragments": 1}}
            },
        }

        response = await self._client.search(index=index, body=body)
        results = []
        for hit in response["hits"]["hits"]:
            results.append({
                "id": hit["_id"],
                "score": hit["_score"],
                "source": hit["_source"],
                "highlight": hit.get("highlight", {}),
            })
        return results

    async def delete_by_document(self, workspace_id: UUID, document_id: str) -> None:
        index = self._index_name(workspace_id)
        await self._client.delete_by_query(
            index=index,
            body={"query": {"term": {"document_id": document_id}}},
        )

    async def aggregate_by_document(self, workspace_id: UUID) -> list[dict]:
        index = self._index_name(workspace_id)
        response = await self._client.search(
            index=index,
            body={
                "size": 0,
                "aggs": {
                    "documents": {
                        "terms": {"field": "document_id", "size": 100}
                    }
                },
            },
        )
        return response.get("aggregations", {}).get("documents", {}).get("buckets", [])
