"""Redis-backed caching and tenant limits.

Implements (see docs/COST_OPTIMIZATION.md and docs/MULTI_TENANCY.md):
- Query embedding cache (24h TTL, workspace-scoped)
- Semantic answer cache (1h TTL, invalidated on workspace document changes)
- Per-user and per-organization sliding-window rate limits
- Per-organization daily token budgets
"""

import hashlib
import json
import time
from datetime import UTC, datetime
from uuid import UUID

import redis.asyncio as aioredis

from app.core.config import Settings, get_settings
from app.core.exceptions import RateLimitError
from app.core.logging import get_logger
from app.core.telemetry import QUERY_COUNT

logger = get_logger(__name__)

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_client


def _normalize_query(query: str) -> str:
    return " ".join(query.lower().split())


class CacheService:
    """All Redis interactions for the request hot path.

    Every method degrades gracefully: a Redis outage must never take chat down,
    it only loses caching and rate limiting (fail-open by design).
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._redis = get_redis()

    # ── Query embedding cache ────────────────────────────────

    def _embedding_key(self, workspace_id: UUID, query: str) -> str:
        digest = hashlib.sha256(
            f"{workspace_id}:{_normalize_query(query)}".encode()
        ).hexdigest()
        return f"emb:{digest}"

    async def get_embedding(self, workspace_id: UUID, query: str) -> list[float] | None:
        if not self._settings.enable_embedding_cache:
            return None
        try:
            cached = await self._redis.get(self._embedding_key(workspace_id, query))
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning("embedding_cache_get_failed", error=str(e))
        return None

    async def set_embedding(
        self, workspace_id: UUID, query: str, embedding: list[float]
    ) -> None:
        if not self._settings.enable_embedding_cache:
            return
        try:
            await self._redis.set(
                self._embedding_key(workspace_id, query),
                json.dumps(embedding),
                ex=self._settings.embedding_cache_ttl_seconds,
            )
        except Exception as e:
            logger.warning("embedding_cache_set_failed", error=str(e))

    # ── Semantic answer cache ────────────────────────────────
    # Keys carry a workspace "generation" counter so a single INCR
    # on document upload/delete invalidates the whole workspace.

    async def _workspace_generation(self, workspace_id: UUID) -> str:
        try:
            gen = await self._redis.get(f"wsgen:{workspace_id}")
            return gen or "0"
        except Exception:
            return "0"

    async def _answer_key(self, workspace_id: UUID, query: str) -> str:
        gen = await self._workspace_generation(workspace_id)
        digest = hashlib.sha256(
            f"{workspace_id}:{gen}:{_normalize_query(query)}".encode()
        ).hexdigest()
        return f"ans:{digest}"

    async def get_answer(self, workspace_id: UUID, query: str) -> dict | None:
        if not self._settings.enable_semantic_cache:
            return None
        try:
            key = await self._answer_key(workspace_id, query)
            cached = await self._redis.get(key)
            if cached:
                QUERY_COUNT.labels(workspace_id=str(workspace_id), status="cache_hit").inc()
                return json.loads(cached)
        except Exception as e:
            logger.warning("answer_cache_get_failed", error=str(e))
        return None

    async def set_answer(self, workspace_id: UUID, query: str, payload: dict) -> None:
        if not self._settings.enable_semantic_cache:
            return
        try:
            key = await self._answer_key(workspace_id, query)
            await self._redis.set(
                key, json.dumps(payload), ex=self._settings.semantic_cache_ttl_seconds
            )
        except Exception as e:
            logger.warning("answer_cache_set_failed", error=str(e))

    async def invalidate_workspace(self, workspace_id: UUID) -> None:
        """Called on any document upload/delete in the workspace."""
        try:
            await self._redis.incr(f"wsgen:{workspace_id}")
            logger.info("workspace_cache_invalidated", workspace_id=str(workspace_id))
        except Exception as e:
            logger.warning("workspace_invalidation_failed", error=str(e))

    # ── Rate limiting (sliding window) ───────────────────────

    async def check_rate_limits(
        self, user_id: UUID, organization_id: UUID | None
    ) -> None:
        """Raises RateLimitError when user or org exceeds their window."""
        now = time.time()
        window = 60.0
        try:
            pipe = self._redis.pipeline()
            user_key = f"rl:user:{user_id}"
            pipe.zremrangebyscore(user_key, 0, now - window)
            pipe.zadd(user_key, {f"{now}": now})
            pipe.zcard(user_key)
            pipe.expire(user_key, 120)

            if organization_id:
                org_key = f"rl:org:{organization_id}"
                pipe.zremrangebyscore(org_key, 0, now - window)
                pipe.zadd(org_key, {f"{now}": now})
                pipe.zcard(org_key)
                pipe.expire(org_key, 120)

            results = await pipe.execute()
            user_count = results[2]
            if user_count > self._settings.user_rate_limit_per_minute:
                raise RateLimitError("User rate limit exceeded")
            if organization_id:
                org_count = results[6]
                if org_count > self._settings.org_rate_limit_per_minute:
                    raise RateLimitError("Organization rate limit exceeded")
        except RateLimitError:
            raise
        except Exception as e:
            # Fail open: Redis outage must not block chat
            logger.warning("rate_limit_check_failed", error=str(e))

    # ── Token budgets ────────────────────────────────────────

    def _budget_key(self, organization_id: UUID) -> str:
        today = datetime.now(UTC).strftime("%Y%m%d")
        return f"budget:{organization_id}:{today}"

    async def check_token_budget(self, organization_id: UUID | None) -> None:
        if not organization_id:
            return
        try:
            spent = await self._redis.get(self._budget_key(organization_id))
            if spent and int(spent) >= self._settings.org_daily_token_budget:
                raise RateLimitError(
                    "Organization daily token budget exceeded. Resets at midnight UTC."
                )
        except RateLimitError:
            raise
        except Exception as e:
            logger.warning("token_budget_check_failed", error=str(e))

    async def record_token_usage(
        self, organization_id: UUID | None, tokens: int
    ) -> None:
        if not organization_id or tokens <= 0:
            return
        try:
            key = self._budget_key(organization_id)
            pipe = self._redis.pipeline()
            pipe.incrby(key, tokens)
            pipe.expire(key, 172800)  # 48h, survives the day boundary
            await pipe.execute()
        except Exception as e:
            logger.warning("token_usage_record_failed", error=str(e))
