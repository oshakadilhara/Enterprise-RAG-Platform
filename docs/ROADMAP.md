# Development Roadmap

## Phase 1: Foundation (Complete)

- [x] Project structure with clean architecture
- [x] FastAPI backend with JWT auth and RBAC
- [x] PostgreSQL schema with multi-tenancy
- [x] React frontend with all core pages
- [x] Docker Compose local development
- [x] Document upload and async processing pipeline
- [x] Text extraction (PDF, DOCX, TXT, CSV)
- [x] Chunking strategies (fixed, recursive, semantic)

## Phase 2: Retrieval Engine (Complete)

- [x] Embedding provider abstraction (OpenAI, Gemini, BGE, ST)
- [x] Qdrant vector storage with collection management
- [x] OpenSearch BM25 full-text search
- [x] Hybrid search with configurable weights
- [x] BGE / Cross-Encoder reranking
- [x] Full retrieval pipeline with query expansion
- [x] LLM provider abstraction (OpenAI, Gemini, Claude, Ollama)
- [x] Citations in responses

## Phase 3: Enterprise Features (Complete)

- [x] Multi-tenant organizations and workspaces
- [x] Workspace member management and invitations
- [x] Chat with streaming responses
- [x] Conversation persistence and search
- [x] Usage analytics and monitoring
- [x] RAG evaluation (RAGAS, DeepEval)
- [x] Rate limiting and audit logging
- [x] Prometheus metrics and OpenTelemetry

## Phase 4: Production Hardening (Next)

Documentation complete — see [docs/README.md](README.md) for scaling, ops, and security guides.

- [ ] Alembic database migrations
- [ ] S3 document storage integration (boto3)
- [ ] PgBouncer deployment (required at 50K users — see [Capacity Planning](CAPACITY_PLANNING.md))
- [x] Cost Tier 1: utility model for expansion, confidence-gated expansion, prompt-cache message ordering, token-based history trim, output cap (see [Cost Optimization](COST_OPTIMIZATION.md))
- [x] XAI Tier 1: citation score breakdown, abstention threshold, persisted retrieval trace (see [Explainable AI](EXPLAINABLE_AI.md))
- [x] Query embedding cache (Redis)
- [x] Semantic answer cache with workspace invalidation
- [x] Org-level rate limits and token budgets (Redis sliding window + daily budgets)
- [ ] Email notifications for invitations
- [ ] WebSocket chat streaming (alternative to SSE)
- [ ] Document preview in UI
- [ ] Advanced workspace permissions (viewer role enforcement)
- [ ] API key authentication for service accounts
- [ ] Comprehensive integration test suite
- [ ] Load testing with Locust (500 QPS target — see [Scaling Architecture](SCALING_ARCHITECTURE.md))

## Phase 5: Advanced RAG (Q2)

- [ ] Parent-child chunking for long documents
- [ ] Multi-modal support (image extraction from PDFs)
- [ ] Agentic RAG with tool use
- [ ] Model routing by query complexity (Cost Tier 3 — requires eval harness)
- [ ] XAI Tier 2: sentence-level attribution, span highlighting in sources
- [ ] Production faithfulness sampling as an SLO (XAI Tier 3)
- [ ] Conversation memory summarization
- [ ] Custom embedding fine-tuning pipeline
- [ ] A/B testing for retrieval strategies
- [ ] Auto-tuning hybrid search weights
- [ ] GraphRAG for entity relationships
- [ ] Real-time collaborative document editing awareness

## Phase 6: Scale & Multi-Region (Q3)

- [ ] Qdrant sharding across workspaces
- [ ] OpenSearch index lifecycle management
- [ ] Read replica routing for PostgreSQL
- [ ] Multi-region active-active deployment
- [ ] CDN caching for static assets and API responses
- [ ] Background re-indexing for model changes
- [ ] Cost optimization dashboard
- [ ] Per-organization usage quotas and billing

## Phase 7: Enterprise Integrations (Q4)

- [ ] SSO/SAML integration (Okta, Azure AD)
- [ ] Slack/Teams bot connectors
- [ ] SharePoint/Google Drive sync
- [ ] Confluence/Notion importers
- [ ] Webhook notifications
- [ ] SCIM user provisioning
- [ ] SOC 2 compliance documentation
- [ ] Data residency controls (EU, US regions)
- [ ] Custom LLM deployment (vLLM, TGI)

## Success Metrics

| Metric | Target |
|--------|--------|
| Retrieval Precision@5 | > 0.85 |
| Answer Faithfulness | > 0.90 |
| P95 Query Latency | < 3s |
| Document Processing | < 30s per 100 pages |
| Uptime | 99.9% |
| Concurrent Users | 10,000+ |
