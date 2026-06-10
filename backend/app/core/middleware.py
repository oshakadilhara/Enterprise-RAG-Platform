"""Application middleware: rate limiting, audit logging, request tracking."""

import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.core.logging import get_logger
from app.core.telemetry import REQUEST_COUNT, REQUEST_LATENCY

logger = get_logger(__name__)

_rate_limit_store: dict[str, list[float]] = defaultdict(list)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in ("/health", "/metrics", "/docs", "/openapi.json"):
            return await call_next(request)

        settings = get_settings()
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = 60.0

        _rate_limit_store[client_ip] = [
            t for t in _rate_limit_store[client_ip] if now - t < window
        ]

        if len(_rate_limit_store[client_ip]) >= settings.rate_limit_per_minute:
            raise RateLimitError()

        _rate_limit_store[client_ip].append(now)
        return await call_next(request)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        endpoint = request.url.path
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code,
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)

        return response


class AuditLogMiddleware(BaseHTTPMiddleware):
    AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if request.method in self.AUDIT_METHODS:
            logger.info(
                "audit_log",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                client_ip=request.client.host if request.client else None,
                request_id=getattr(request.state, "request_id", None),
                timestamp=datetime.now(UTC).isoformat(),
            )

        return response
