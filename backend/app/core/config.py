"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Enterprise RAG Platform"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = Field(..., min_length=32)
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str | None = None
    qdrant_collection_prefix: str = "rag_"

    # OpenSearch
    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    opensearch_user: str = "admin"
    opensearch_password: str = "admin"
    opensearch_index_prefix: str = "rag_"
    opensearch_use_ssl: bool = False

    # S3
    s3_bucket: str = "rag-documents"
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    # Embedding
    embedding_provider: Literal["openai", "gemini", "bge", "sentence_transformers"] = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # LLM
    llm_provider: Literal["openai", "gemini", "claude", "ollama"] = "openai"
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    # Cheap model for internal calls (query expansion, classification).
    # Cost Tier 1 — see docs/COST_OPTIMIZATION.md
    llm_utility_model: str = "gpt-4o-mini"
    # Cap answer output tokens (output costs 4x input)
    answer_max_tokens: int = 1024
    # Cap chat history by tokens, not message count
    history_max_tokens: int = 800

    # API Keys
    openai_api_key: str | None = None
    google_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # Reranker
    reranker_provider: Literal["bge", "cross_encoder"] = "bge"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # Hybrid Search
    vector_search_weight: float = 0.6
    bm25_search_weight: float = 0.4
    hybrid_top_k: int = 50
    rerank_top_k: int = 5

    # Retrieval confidence / XAI — see docs/EXPLAINABLE_AI.md
    # Skip query expansion when top vector score >= this (Cost Tier 1)
    expansion_confidence_threshold: float = 0.7
    # Abstain from LLM generation when top rerank score < this
    retrieval_confidence_threshold: float = 0.3
    abstain_on_low_confidence: bool = True

    # Caching — see docs/COST_OPTIMIZATION.md
    enable_embedding_cache: bool = True
    embedding_cache_ttl_seconds: int = 86400  # 24h
    enable_semantic_cache: bool = True
    semantic_cache_ttl_seconds: int = 3600  # 1h

    # Per-organization limits (multi-tenant fairness)
    org_rate_limit_per_minute: int = 500
    user_rate_limit_per_minute: int = 30
    org_daily_token_budget: int = 2_000_000

    # Chunking
    chunking_strategy: Literal["fixed", "recursive", "semantic"] = "recursive"
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Rate Limiting
    rate_limit_per_minute: int = 60

    # Observability
    otel_exporter_otlp_endpoint: str | None = None
    prometheus_enabled: bool = True

    # CORS
    cors_origins: str = "http://localhost:5173"

    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: str) -> list[str]:
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def opensearch_url(self) -> str:
        scheme = "https" if self.opensearch_use_ssl else "http"
        return f"{scheme}://{self.opensearch_host}:{self.opensearch_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
