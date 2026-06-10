"""OpenTelemetry and Prometheus instrumentation."""

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings

# Prometheus metrics
REQUEST_COUNT = Counter(
    "rag_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "rag_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)

QUERY_COUNT = Counter(
    "rag_queries_total",
    "Total RAG queries",
    ["workspace_id", "status"],
)

RETRIEVAL_LATENCY = Histogram(
    "rag_retrieval_duration_seconds",
    "Retrieval pipeline latency",
    ["stage"],
)

TOKEN_USAGE = Counter(
    "rag_token_usage_total",
    "Total tokens consumed",
    ["provider", "type"],
)

EMBEDDING_LATENCY = Histogram(
    "rag_embedding_duration_seconds",
    "Embedding generation latency",
    ["provider"],
)

DOCUMENT_PROCESSING = Counter(
    "rag_documents_processed_total",
    "Documents processed",
    ["status", "file_type"],
)


def setup_telemetry(app) -> None:
    settings = get_settings()
    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            resource = Resource.create({"service.name": "rag-platform"})
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            pass

    if settings.prometheus_enabled:
        @app.get("/metrics")
        async def metrics():
            return PlainTextResponse(
                generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
            )
