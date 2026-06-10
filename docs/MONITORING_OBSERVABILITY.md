# Monitoring & Observability

Production observability strategy for 100K users. The goal is not more dashboards — it is **actionable signal** that prevents outages and controls cost.

## Observability Pillars

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   METRICS   │  │    LOGS     │  │   TRACES    │  │   ALERTS    │
│  Prometheus │  │  structlog  │  │ OpenTelemetry│  │  Grafana    │
│  (what)     │  │  (why)      │  │  (where)    │  │  (act)      │
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

---

## Service Level Objectives (SLOs)

| SLI | SLO Target | Measurement Window | Error Budget |
|-----|-----------|-------------------|--------------|
| API availability | 99.9% | 30 days | 43.2 min downtime |
| Chat p95 latency | < 3 seconds | 7 days | 5% of queries |
| Chat p99 latency | < 8 seconds | 7 days | 1% of queries |
| Retrieval p95 | < 500ms | 7 days | 5% of queries |
| Ingestion success rate | > 99% | 7 days | 1% of uploads |
| Data isolation | 0 breaches | Forever | 0 |

### SLO Burn Rate Alerts

```
Fast burn (1h):  2% of monthly budget in 1 hour  → Page on-call
Slow burn (6h):  5% of monthly budget in 6 hours → Ticket + investigate
```

---

## Metrics Catalog

### API Layer

| Metric | Type | Labels | Alert Threshold |
|--------|------|--------|-----------------|
| `rag_http_requests_total` | Counter | method, endpoint, status | error rate > 1% |
| `rag_http_request_duration_seconds` | Histogram | method, endpoint | p95 > 2s |
| `rag_active_sse_connections` | Gauge | pod | > 800 per pod |

### RAG Pipeline

| Metric | Type | Labels | Alert Threshold |
|--------|------|--------|-----------------|
| `rag_queries_total` | Counter | workspace_id, status | error rate > 2% |
| `rag_retrieval_duration_seconds` | Histogram | stage | p95 > 500ms per stage |
| `rag_embedding_duration_seconds` | Histogram | provider | p95 > 200ms |
| `rag_token_usage_total` | Counter | provider, type | daily > budget × 0.8 |
| `rag_documents_processed_total` | Counter | status, file_type | failure rate > 1% |
| `rag_cache_hit_total` | Counter | cache_type | hit rate < 15% (investigate) |
| `rag_rerank_pairs_total` | Counter | — | — |
| `rag_hybrid_search_results` | Histogram | source | avg < 10 (sparse index) |

### Infrastructure

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| `pg_connections_active` | RDS | > 70% max |
| `redis_memory_used_bytes` | ElastiCache | > 80% |
| `qdrant_search_latency_ms` | Qdrant API | p95 > 80ms |
| `opensearch_search_latency_ms` | OS API | p95 > 60ms |
| `celery_queue_length` | Redis | > 200 (high), > 1000 (critical) |
| `celery_task_runtime_seconds` | Worker | p95 > 120s |

---

## Structured Logging

### Log Format (JSON)

```json
{
  "timestamp": "2026-06-10T14:30:00Z",
  "level": "info",
  "event": "rag_query_completed",
  "request_id": "abc-123",
  "user_id": "uuid",
  "organization_id": "uuid",
  "workspace_id": "uuid",
  "query_length": 45,
  "retrieval_ms": 320,
  "llm_ms": 1850,
  "total_ms": 2340,
  "chunks_retrieved": 5,
  "tokens_input": 2800,
  "tokens_output": 450,
  "model": "gpt-4o",
  "cache_hit": false
}
```

### What to Log

| Event | Level | Fields |
|-------|-------|--------|
| `rag_query_completed` | INFO | latency breakdown, tokens, model |
| `rag_query_failed` | ERROR | error type, stage, workspace_id |
| `document_processed` | INFO | doc_id, chunks, duration |
| `document_processing_failed` | ERROR | doc_id, error, file_type |
| `auth_login` | INFO | user_id, ip (no password) |
| `auth_failed` | WARN | email, ip, reason |
| `rate_limit_exceeded` | WARN | org_id, user_id, limit_type |
| `audit_log` | INFO | action, resource, user_id |

### What NOT to Log

- Query content (PII risk) — log hash only
- Chunk content — log chunk_id only
- LLM responses — log token count only
- Passwords, tokens, API keys — never

---

## Distributed Tracing

### Trace Spans per Query

```
rag.query [2300ms]
  ├── auth.verify [5ms]
  ├── retrieval.pipeline [350ms]
  │   ├── retrieval.query_expansion [120ms]
  │   ├── retrieval.embedding [80ms]
  │   ├── retrieval.vector_search [45ms]
  │   ├── retrieval.bm25_search [35ms]
  │   └── retrieval.rerank [250ms]
  ├── llm.generate [1900ms]
  │   ├── llm.first_token [800ms]
  │   └── llm.completion [1100ms]
  └── db.save_message [15ms]
```

### Sampling Strategy

| Scale | Sample Rate | Rationale |
|-------|-------------|-----------|
| <10K users | 100% | Full visibility during growth |
| 10K–50K | 10% | Balance cost vs coverage |
| 50K–100K | 1% + 100% errors | Cost control, always trace failures |

Always trace (100%):
- Errors and timeouts
- Latency > p99 threshold
- First query per user per day (cold path)

---

## Grafana Dashboards

### Dashboard 1: Platform Health
- Request rate (QPS) — real-time
- Error rate (%) — 5-min rolling
- p50/p95/p99 latency — by endpoint
- Active SSE connections
- Pod count (per deployment)

### Dashboard 2: RAG Pipeline
- Queries per minute — by organization (top 10)
- Retrieval latency breakdown — stacked by stage
- Cache hit rate — embedding + semantic
- Reranker latency and throughput
- Chunks retrieved per query — distribution

### Dashboard 3: Cost & Usage
- Token usage per hour — by provider
- Daily cost estimate — rolling 30 days
- Top 10 organizations by token spend
- Token budget utilization (%) — by org tier
- Embedding API calls — by provider

### Dashboard 4: Ingestion
- Documents processed per hour — by status
- Celery queue depth — by queue name
- Processing time distribution — by file type
- Worker utilization — CPU/GPU
- Failed documents — with error categories

### Dashboard 5: Infrastructure
- PostgreSQL connections, CPU, IOPS
- Redis memory, hit rate, connections
- Qdrant search latency, collection count
- OpenSearch search latency, index count
- Node CPU/memory/disk — per service

---

## Alert Definitions

### P1 — Page Immediately (Production Down)

| Alert | Condition | Runbook |
|-------|-----------|---------|
| API Down | Health check fails 3× in 2 min | [Runbook: API Down](OPERATIONS_RUNBOOK.md) |
| Error Rate Critical | > 5% for 5 min | [Runbook: High Errors](OPERATIONS_RUNBOOK.md) |
| PostgreSQL Unreachable | Connection failures > 10 in 1 min | [Runbook: DB Failure](OPERATIONS_RUNBOOK.md) |
| Data Isolation Breach | Cross-tenant access detected | [Runbook: Security Incident](OPERATIONS_RUNBOOK.md) |

### P2 — Page During Business Hours

| Alert | Condition | Runbook |
|-------|-----------|---------|
| Latency Degraded | p95 > 3s for 15 min | Scale API pods |
| LLM Provider Down | Error rate > 10% for 5 min | Enable fallback provider |
| Celery Backlog | Queue > 1000 for 30 min | Scale workers |
| Token Budget Exceeded | Org at 100% daily budget | Notify org admin |

### P3 — Ticket Next Business Day

| Alert | Condition | Action |
|-------|-----------|--------|
| Cache Hit Rate Low | < 15% for 24h | Investigate cache config |
| Retrieval Quality Drop | Precision@5 < 0.80 weekly | Review eval results |
| Disk Usage High | > 75% on any node | Plan expansion |
| Certificate Expiry | < 14 days | Renew cert |

---

## Cost Monitoring

### Daily Cost Report (Automated)

```
Organization: Acme Corp (Business tier)
Date: 2026-06-10

Queries: 4,521
Tokens:  12.4M input / 2.1M output
Est. cost: $142.50
Budget: $200/day (71% utilized)

Top workspaces by cost:
  1. Engineering Docs — $58.20 (41%)
  2. HR Policies — $31.40 (22%)
  3. Legal Contracts — $28.90 (20%)
```

### Anomaly Detection

Alert when:
- Org daily cost > 3× their 30-day average
- Single user > 20% of org daily queries
- Workspace query rate doubles in 1 hour (possible bot)

---

## Observability Maturity Path

| Stage | Users | Capability |
|-------|-------|------------|
| 1 | 0–10K | Prometheus + Grafana + structured logs |
| 2 | 10K–50K | OpenTelemetry tracing + SLO dashboards |
| 3 | 50K–100K | Cost attribution + anomaly detection |
| 4 | 100K+ | ML-based capacity forecasting + auto-remediation |

See [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) for incident response procedures.
