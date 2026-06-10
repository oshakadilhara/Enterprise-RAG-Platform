# Architecture Documentation

## System Overview

The Enterprise RAG Platform follows **Clean Architecture** with **Domain-Driven Design** principles. The system is designed to scale to 100,000 users and 100 million document chunks across multi-region deployments.

## Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Presentation Layer                    │
│  React SPA │ FastAPI Routes │ SSE Streaming │ OpenAPI  │
├─────────────────────────────────────────────────────────┤
│                    Application Layer                     │
│  AuthService │ ChatService │ DocumentService │ Pipeline │
├─────────────────────────────────────────────────────────┤
│                      Domain Layer                        │
│  Entities │ Interfaces │ Events │ Value Objects          │
├─────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                   │
│  PostgreSQL │ Qdrant │ OpenSearch │ Redis │ S3 │ Celery │
└─────────────────────────────────────────────────────────┘
```

## Backend Architecture

### Core (`app/core/`)
- **config.py** — Pydantic settings from environment
- **security.py** — JWT, RBAC, password hashing
- **dependencies.py** — FastAPI DI, auth middleware
- **middleware.py** — Rate limiting, audit logs, metrics
- **telemetry.py** — OpenTelemetry + Prometheus

### Domain (`app/domain/`)
- **entities/** — RetrievalContext, SearchResult
- **interfaces/** — EmbeddingProvider, LLMProvider, Reranker

### Services (`app/services/`)

#### Ingestion Pipeline
```
Upload → Validate → Extract → Clean → Chunk → Embed → Store
                                              ├→ Qdrant (vectors)
                                              └→ OpenSearch (text)
```

#### Retrieval Pipeline
```
Query → Expand → Embed → Hybrid Search → Rerank → Context → LLM
                          ├→ Vector (Qdrant)
                          └→ BM25 (OpenSearch)
```

### Repository Pattern
All database access goes through repositories (`app/repositories/`), keeping services decoupled from ORM details.

## Frontend Architecture

```
src/
├── pages/          # Route-level components
├── components/
│   ├── ui/         # ShadCN primitives
│   └── layout/     # Sidebar, AppLayout
├── stores/         # Zustand (auth, app state)
├── lib/            # API client, utilities
├── hooks/          # Custom React hooks
└── types/          # TypeScript interfaces
```

**State Management:**
- **Zustand** — Auth tokens, current workspace
- **React Query** — Server state, caching, mutations

## Data Flow

### Document Upload
1. User uploads file via React → FastAPI multipart endpoint
2. File saved to local/S3 storage, metadata in PostgreSQL
3. Celery task queued for async processing
4. Worker: extract → chunk → embed → index in Qdrant + OpenSearch
5. Document status updated to `completed`

### Chat Query
1. User sends message → ChatService
2. RetrievalPipeline: expand query → hybrid search → rerank
3. Top 5 chunks form context
4. LLM generates answer with citation instructions
5. Response saved with citations JSON
6. Usage metrics recorded

## Multi-Tenancy

```
Organization (tenant)
  └── Workspaces (knowledge domains)
        ├── Documents
        ├── Members (with roles)
        └── Conversations
```

- Each workspace gets isolated Qdrant collection and OpenSearch index
- Organization-level usage tracking and billing
- RBAC enforced at API layer via permission checks

## Scalability Design

Designed for **100,000 users**, **100M chunks**, and **500 QPS peak**. See dedicated scaling documentation for full analysis.

| Component | Scaling Strategy |
|-----------|-----------------|
| FastAPI | Horizontal (15–30 K8s replicas, SSE-aware) |
| Celery Workers | Queue-based, GPU tier for embedding |
| PostgreSQL | PgBouncer + RDS read replicas + partitioning |
| Qdrant | Workspace-scoped collections, 12-node cluster |
| OpenSearch | Per-workspace indexes, 9 data nodes |
| Redis | Cluster mode (cache + broker + rate limits) |
| LLM | Gateway with provider failover + token budgets |

**Scaling documents:**
- [Scaling Architecture](SCALING_ARCHITECTURE.md) — How every component scales
- [Capacity Planning](CAPACITY_PLANNING.md) — QPS, storage, and cost calculations
- [RAG Engineering](RAG_ENGINEERING.md) — Retrieval pipeline at 100M chunks
- [Multi-Tenancy](MULTI_TENANCY.md) — Tenant isolation and fair scheduling

### Critical Scaling Principles

1. **Never search 100M chunks globally** — workspace-scoped indexes reduce search space by 99%+
2. **PgBouncer is mandatory at 50K+ users** — PostgreSQL connection exhaustion is the #1 outage cause
3. **LLM cost dominates** (~$375K/month at full scale) — semantic caching and token budgets are required
4. **Ingestion is async with backpressure** — never block the upload API on embedding
5. **Per-organization rate limits** — IP-level limits are insufficient for multi-tenant fairness

## Observability Stack

- **Structured Logging** — JSON via structlog
- **Metrics** — Prometheus (request latency, query count, token usage)
- **Tracing** — OpenTelemetry OTLP export
- **Audit Logs** — All POST/PUT/PATCH/DELETE operations
- **Dashboards** — Grafana with pre-built RAG metrics

## Security Architecture

- JWT with short-lived access tokens (30 min) + refresh tokens (7 days)
- RBAC with hierarchical roles and granular permissions
- Rate limiting per organization + user (not just IP)
- Input validation via Pydantic schemas
- File upload validation (type, size, content)
- Audit trail for compliance

See [Security & Compliance](SECURITY_COMPLIANCE.md) and [Multi-Tenancy](MULTI_TENANCY.md).

## Operations

- [Operations Runbook](OPERATIONS_RUNBOOK.md) — Incident response procedures
- [Monitoring & Observability](MONITORING_OBSERVABILITY.md) — SLOs, metrics, alerts
- [Disaster Recovery](DISASTER_RECOVERY.md) — RPO/RTO, failover, degraded modes
- [Deployment Guide](DEPLOYMENT_GUIDE.md) — Production rollout
- [AWS Architecture](AWS_ARCHITECTURE.md) — Cloud deployment on EKS
