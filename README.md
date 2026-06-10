# Enterprise RAG Platform

Production-grade, multi-tenant AI knowledge assistant for internal company documents. Built with clean architecture, hybrid retrieval, and enterprise security.

## Features

- **Multi-tenant** organization and workspace management
- **Document ingestion** — PDF, DOCX, TXT, CSV with async processing
- **Hybrid search** — Vector (Qdrant) + BM25 (OpenSearch) with configurable weights
- **Reranking** — BGE / Cross-Encoder models for precision
- **Multi-provider AI** — OpenAI, Gemini, Claude, Ollama (LLM) + OpenAI, Gemini, BGE, Sentence Transformers (embeddings)
- **Citations** — Every answer includes source document, page number, and relevance score
- **RBAC** — Super Admin, Org Admin, Manager, Employee roles
- **Observability** — OpenTelemetry, Prometheus, structured logging, audit trails
- **Evaluation** — RAGAS and DeepEval metrics

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   React UI  │────▶│   FastAPI    │────▶│  PostgreSQL     │
│  (Vite/TS)  │     │   Backend    │     │  (Metadata)     │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌──────────┐
        │ Qdrant  │  │OpenSearch│  │  Redis   │
        │(Vectors)│  │ (BM25)  │  │ (Queue)  │
        └─────────┘  └─────────┘  └──────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
              ┌──────────┐  ┌──────────┐
              │ Celery   │  │ LLM APIs │
              │ Workers  │  │ Embed API│
              └──────────┘  └──────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for local frontend dev)
- Python 3.12+ (for local backend dev)

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env with your API keys (OPENAI_API_KEY, etc.)
```

### 2. Start with Docker Compose

```bash
docker compose up -d
```

Services:
| Service     | URL                    |
|-------------|------------------------|
| Frontend    | http://localhost:5173  |
| Backend API | http://localhost:8000  |
| API Docs    | http://localhost:8000/docs |
| Prometheus  | http://localhost:9090  |
| Grafana     | http://localhost:3001  |
| MinIO       | http://localhost:9001  |

### 3. Local development (without Docker)

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Worker:**
```bash
cd backend
celery -A app.workers.celery_app worker --loglevel=info
```

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST API endpoints
│   │   ├── core/            # Config, security, middleware
│   │   ├── domain/          # Entities and interfaces (DDD)
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── repositories/    # Data access layer
│   │   ├── schemas/         # Pydantic API contracts
│   │   ├── services/        # Business logic
│   │   │   ├── embedding/   # Embedding providers
│   │   │   ├── llm/         # LLM providers
│   │   │   ├── ingestion/   # Document pipeline
│   │   │   ├── retrieval/   # Hybrid search + rerank
│   │   │   ├── vector/      # Qdrant service
│   │   │   └── search/      # OpenSearch service
│   │   └── workers/         # Celery async tasks
│   └── tests/
├── frontend/
│   └── src/
│       ├── pages/           # Login, Dashboard, Chat, etc.
│       ├── components/      # UI components (ShadCN)
│       ├── stores/          # Zustand state
│       └── lib/             # API client
├── infrastructure/
│   ├── kubernetes/        # K8s manifests
│   └── aws/               # AWS architecture docs
├── docs/                  # Detailed documentation
└── docker-compose.yml
```

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register user/org |
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/refresh` | Refresh token |
| GET | `/api/v1/workspaces` | List workspaces |
| POST | `/api/v1/documents/upload` | Upload document |
| POST | `/api/v1/chat` | Send chat message |
| POST | `/api/v1/chat/stream` | Stream chat (SSE) |
| GET | `/api/v1/analytics/usage` | Usage metrics |

See [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) for full API documentation.

## Retrieval Pipeline

```
Question → Query Expansion → Embedding → Hybrid Search (Vector + BM25)
    → Top 50 → Reranker → Top 5 → Context Building → LLM Response + Citations
```

Configurable via environment:
- `VECTOR_SEARCH_WEIGHT=0.6`
- `BM25_SEARCH_WEIGHT=0.4`
- `CHUNKING_STRATEGY=recursive` (fixed | recursive | semantic)

## Security

- JWT access + refresh tokens
- RBAC with 4 role levels
- Rate limiting (60 req/min default)
- Audit logging for all mutations
- Input validation on all endpoints
- Secure file upload with type/size checks

## Deployment

- **Local:** Docker Compose
- **Staging/Production:** Kubernetes (see `infrastructure/kubernetes/`)
- **Cloud:** AWS EKS architecture (see `docs/AWS_ARCHITECTURE.md`)

## Documentation

Full documentation hub: **[docs/README.md](docs/README.md)**

### Core
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Database Schema](docs/DATABASE_SCHEMA.md)
- [API Contracts](docs/API_CONTRACTS.md)
- [Frontend Architecture](docs/FRONTEND_ARCHITECTURE.md)

### Scaling to 100K Users
- [Scaling Architecture](docs/SCALING_ARCHITECTURE.md) — Component scaling, caching, autoscaling
- [Capacity Planning](docs/CAPACITY_PLANNING.md) — QPS math, sizing, cost models
- [RAG Engineering Guide](docs/RAG_ENGINEERING.md) — Retrieval at 100M chunks
- [Multi-Tenancy & Isolation](docs/MULTI_TENANCY.md) — Noisy neighbor prevention
- [Cost Optimization](docs/COST_OPTIMIZATION.md) — Reducing LLM API spend 45–70%
- [Explainable AI](docs/EXPLAINABLE_AI.md) — Citations, confidence, audit traceability

### Operations
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [AWS Architecture](docs/AWS_ARCHITECTURE.md)
- [Operations Runbook](docs/OPERATIONS_RUNBOOK.md)
- [Monitoring & Observability](docs/MONITORING_OBSERVABILITY.md)
- [Disaster Recovery](docs/DISASTER_RECOVERY.md)
- [Security & Compliance](docs/SECURITY_COMPLIANCE.md)
- [Development Roadmap](docs/ROADMAP.md)

## License

Proprietary — Enterprise RAG Platform
