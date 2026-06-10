# Scaling Architecture — 100,000 Users

This document defines how the Enterprise RAG Platform scales from pilot (1K users) to enterprise production (100K users) without architectural rewrites. Every decision here is driven by measured bottlenecks, not premature optimization.

## Executive Summary

At 100K registered users, the platform must sustain:

| Metric | Value | Implication |
|--------|-------|-------------|
| Peak concurrent sessions | ~10,000 | Stateless API horizontal scaling |
| Sustained query QPS | ~50–100 | Retrieval + LLM pipeline tuning |
| Peak query QPS | ~500 | Burst handling via queue + cache |
| Daily queries | ~1,000,000 | Cost governance mandatory |
| Total chunks | ~100,000,000 | Workspace-partitioned vector + text indexes |
| Daily ingestion | ~50,000 documents | Dedicated worker fleet with GPU tier |

**Core principle:** Scale the bottleneck, not everything. In RAG systems at enterprise scale, the bottleneck shifts over time:

```
Phase 1 (0–10K users):   LLM API latency + rate limits
Phase 2 (10K–50K users): Vector search + reranker throughput
Phase 3 (50K–100K users): PostgreSQL connections + multi-tenant noisy neighbors
Phase 4 (100M chunks):   Index management + embedding re-index cost
```

---

## Scaling Topology

### Target Production Architecture (100K Users)

```
                         ┌──────────────┐
                         │  CloudFront  │
                         │  + WAF       │
                         └──────┬───────┘
                                │
                    ┌───────────▼───────────┐
                    │   ALB (multi-AZ)        │
                    │   sticky: SSE only      │
                    └───────────┬───────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
  ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
  │ API Tier    │       │ API Tier    │       │ API Tier    │
  │ 10–20 pods  │       │ (HPA)       │       │ m5.xlarge   │
  └──────┬──────┘       └──────┬──────┘       └──────┬──────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │
    ┌──────────────────────────┼──────────────────────────┐
    ▼              ▼           ▼           ▼              ▼
┌────────┐  ┌──────────┐ ┌─────────┐ ┌─────────┐  ┌──────────┐
│PgBouncer│  │  Redis   │ │ Qdrant  │ │OpenSearch│  │ LLM GW  │
│ pool    │  │ Cluster  │ │ Cluster │ │ Cluster  │  │ + Cache │
└────┬───┘  └────┬─────┘ └────┬────┘ └────┬────┘  └────┬─────┘
     │           │            │           │            │
┌────▼────┐ ┌────▼────┐       │           │       ┌────▼────┐
│ RDS PG  │ │ Celery  │       │           │       │ OpenAI  │
│ Primary │ │ Workers │       │           │       │ Bedrock │
│ + 2 RR  │ │ 4–16 GPU│       │           │       │ Gemini  │
└─────────┘ └─────────┘       │           │       └─────────┘
                              │           │
                    workspace-scoped collections
                    (never cross-workspace search)
```

---

## Component Scaling Strategies

### 1. API Layer (FastAPI)

**Profile:** I/O-bound, stateless, SSE streaming for chat.

| Stage | Replicas | Trigger |
|-------|----------|---------|
| 10K users | 3 | Baseline |
| 50K users | 8 | CPU > 60% or p95 > 2s |
| 100K users | 15–20 | HPA on request rate + latency |

**Configuration:**
```yaml
# HPA targets
metrics:
  - type: Resource
    resource:
      name: cpu
      targetAverageUtilization: 65
  - type: Pods
    pods:
      metric:
        name: rag_http_request_duration_seconds_p95
      target:
        type: AverageValue
        averageValue: "2"
```

**Critical rules:**
- Never run embedding or reranker models inside API pods at 100K scale — offload to dedicated services
- SSE connections are long-lived; size pods for **concurrent connections**, not just QPS
- Use `uvicorn` with multiple workers per pod: `--workers 4` on m5.xlarge (4 vCPU)

**Connection math:**
- 10K concurrent users × 1 SSE stream = 10K open connections
- Each API pod handles ~500–1000 SSE connections safely
- Required pods for chat peak: **10–20 minimum**

---

### 2. Retrieval Layer (The AI Hot Path)

Retrieval is the highest-compute path per query. Budget per query at p50:

| Stage | Target Latency | Scale Strategy |
|-------|---------------|----------------|
| Query embedding | 50–150ms | Cache + batch API |
| Vector search (Qdrant) | 30–80ms | Workspace filter + HNSW |
| BM25 search (OpenSearch) | 20–60ms | Workspace index routing |
| Reranker (top 50 → 5) | 100–300ms | Dedicated CPU worker pool |
| LLM generation | 800–2000ms | Streaming + provider routing |
| **Total p50** | **~1.5s** | |
| **Total p95** | **< 3s** | |

#### Query Embedding Cache

At 100K users, ~30% of queries are near-duplicates (same workspace, similar phrasing).

```
Cache key: SHA256(workspace_id + normalized_query)
TTL: 24 hours (workspace-scoped)
Store: Redis Cluster
Expected hit rate: 25–35%
Savings: ~100ms + embedding API cost per hit
```

#### Parallel Hybrid Search

Vector and BM25 searches are **independent** — always run in parallel:

```python
vector_results, bm25_results = await asyncio.gather(
    qdrant.search(workspace_id, query_vector, top_k=50),
    opensearch.search(workspace_id, query, top_k=50),
)
```

This cuts retrieval stage latency by ~40% vs sequential.

---

### 3. Vector Store (Qdrant) — 100M Chunks

**Partitioning strategy:** One collection per workspace (current design) works up to ~500K chunks/workspace. Beyond that, shard within workspace.

| Scale | Collections | Avg Chunks/Collection | Qdrant Nodes |
|-------|-------------|----------------------|--------------|
| 10K users | ~2,000 | ~5,000 | 3 nodes |
| 50K users | ~10,000 | ~20,000 | 6 nodes |
| 100K users | ~20,000 | ~50,000 | 12 nodes |

**Why workspace isolation matters:**

Searching 100M vectors globally with post-filter is **O(n)** filter penalty — unacceptable at scale. Workspace-scoped collections reduce search space by 99%+ for typical queries.

**Qdrant cluster sizing (100K users):**
```
Nodes: 12 × r6gd.2xlarge (64GB RAM, NVMe)
Replication factor: 2
HNSW config:
  m: 16
  ef_construct: 128
  ef_search: 64 (tune for recall vs latency)
Expected search latency: 20–50ms at 50K vectors/collection
```

**Re-index strategy:** When embedding model changes, run background re-index per workspace with blue/green collection swap — never block live queries.

---

### 4. OpenSearch — 100M Documents

**Index strategy:** One index per workspace with alias routing.

| Concern | Solution |
|---------|----------|
| Index count (20K workspaces) | Index Lifecycle Management (ILM) + cold tier |
| Large workspace (>1M chunks) | Split into time-based sub-indexes |
| Search latency | Limit `top_k` to 50, disable deep pagination |
| Cluster sizing | 9 data nodes × r6g.2xlarge.search |

**Shard formula:**
```
shards = max(1, chunk_count / 30_000_000)  # 30M docs per shard max
replicas = 1 (production minimum)
```

---

### 5. PostgreSQL — Metadata at 100K Users

PostgreSQL stores metadata only — never chunk content at scale (content lives in Qdrant/OpenSearch).

**Projected table sizes at 100K users:**

| Table | Rows | Size |
|-------|------|------|
| users | 100,000 | ~50 MB |
| organizations | 5,000 | ~5 MB |
| workspaces | 25,000 | ~25 MB |
| documents | 2,500,000 | ~2 GB |
| document_chunks | 100,000,000 | ~15 GB (metadata only) |
| messages | 50,000,000 | ~25 GB |
| usage_metrics | 500,000,000 | ~80 GB (partitioned) |

**Mandatory at 50K+ users:**
- **PgBouncer** — transaction pooling, 2000 client connections → 100 DB connections
- **Read replicas** — 2 replicas for analytics, conversation history, document listing
- **Table partitioning** — `usage_metrics` and `audit_logs` by month
- **Archival** — messages older than 12 months → S3 cold storage

```sql
-- Partition usage_metrics by month
CREATE TABLE usage_metrics (
    ...
) PARTITION BY RANGE (created_at);
```

---

### 6. Celery Workers — Ingestion Fleet

Ingestion is **throughput-bound**, not latency-bound. Size for daily batch, not peak second.

| Stage | Workers | Instance | Purpose |
|-------|---------|----------|---------|
| Extract + chunk | 8–16 | c5.2xlarge (CPU) | PDF/DOCX parsing |
| Embed + index | 4–8 | g5.xlarge (GPU) | Batch embedding |
| Evaluation | 2 | c5.4xlarge | RAGAS/DeepEval offline |

**Queue architecture:**
```
ingestion-high    ← user-triggered uploads (priority)
ingestion-bulk    ← bulk imports, connector syncs
ingestion-reindex ← model change re-indexing (lowest)
evaluation        ← offline eval runs
```

**Backpressure:** When `ingestion-high` queue depth > 500, return HTTP 503 with `Retry-After` on upload endpoint. Never unbounded queue growth.

**Throughput target:** 50,000 documents/day = ~0.6 docs/sec average, ~5 docs/sec peak. With 16 workers averaging 30 sec/doc, capacity = ~32 docs/sec — sufficient headroom.

---

### 7. Redis Cluster

| Use Case | Memory | Pattern |
|----------|--------|---------|
| Celery broker | 4 GB | Lists per queue |
| Query embedding cache | 8 GB | Hash per workspace |
| Rate limit counters | 2 GB | Sliding window per org |
| Session/token blocklist | 1 GB | TTL-based |
| Semantic answer cache | 16 GB | Optional, high ROI |

**Cluster:** 6 nodes × cache.r6g.large (13GB each) = ~78 GB total.

---

### 8. LLM Gateway — Cost & Rate Control

At 1M queries/day with avg 3K tokens/query = **3B tokens/day**. This is the largest cost and failure surface.

**Gateway responsibilities:**
1. Provider routing with fallback (OpenAI → Bedrock → Gemini)
2. Per-organization token budgets (daily/monthly caps)
3. Circuit breaker per provider (5 failures → 60s cooldown)
4. Request queuing during provider rate limits
5. Response caching for identical context+query hashes

**Token budget example:**
```
Organization tier:
  Starter:  100K tokens/day
  Business: 1M tokens/day
  Enterprise: 10M tokens/day (negotiated)
```

**Cost projection at 100K users (1M queries/day):**
```
Avg input: 2,000 tokens (context + history)
Avg output: 500 tokens
Daily: 2.5B tokens
At GPT-4o pricing (~$5/1M input, $15/1M output):
  Input:  $10,000/day
  Output: $7,500/day
  Total:  ~$17,500/day → ~$525K/month

Mitigation:
  - Semantic cache (15% hit rate): -$78K/month
  - Smaller model for query expansion: -$20K/month
  - Context compression (reduce top-5 chunk size): -$50K/month
  - Effective cost: ~$375K/month at full utilization
```

---

## Multi-Tenant Fairness (Noisy Neighbor Prevention)

At 100K users across 5,000 organizations, one tenant can destabilize the platform.

| Control | Scope | Limit |
|---------|-------|-------|
| Rate limit | User | 30 queries/min |
| Rate limit | Organization | 500 queries/min |
| Upload throttle | Organization | 100 docs/hour |
| Token budget | Organization | Tier-based daily cap |
| Worker fair scheduling | Celery | Max 20% queue per org |
| Retrieval timeout | Per query | 5s hard limit |
| LLM timeout | Per query | 30s with streaming |

Implement **organization-level circuit breakers**: if an org exceeds 3× their token budget, degrade to retrieval-only responses (no LLM) until next billing period.

---

## Caching Strategy (Three Layers)

```
Layer 1: CDN (CloudFront)
  → Static frontend assets
  → Cache GET /workspaces, /documents (short TTL, user-scoped)

Layer 2: Redis (Application)
  → Query embeddings (24h TTL, workspace-scoped)
  → Rate limit counters
  → Provider health status

Layer 3: Semantic Answer Cache
  → Key: hash(workspace_id + query + top_chunk_ids)
  → TTL: 1 hour (invalidate on document upload to workspace)
  → Expected hit rate: 10–15%
  → Saves full retrieval + LLM on hit
```

**Cache invalidation rule:** Any document upload/delete to workspace `W` invalidates all cache keys prefixed `W:*`.

---

## Autoscaling Policies

| Service | Min | Max | Scale Trigger |
|---------|-----|-----|---------------|
| API pods | 5 | 30 | CPU 65%, p95 latency 2s, SSE connections 800/pod |
| Celery CPU workers | 4 | 32 | Queue depth > 100 for 5 min |
| Celery GPU workers | 2 | 8 | `ingestion-high` depth > 50 |
| Reranker service | 2 | 10 | p95 rerank latency > 400ms |
| Qdrant | 6 | 16 | Search p95 > 80ms |
| OpenSearch | 6 | 12 | Search queue > 200 |

---

## Phased Rollout Path

### Phase A: 0 → 10K Users (Current Architecture)
- Single-region, Docker Compose → K8s
- Per-workspace Qdrant collections
- In-memory rate limiting acceptable
- Single PostgreSQL instance acceptable
- **No changes needed to application code**

### Phase B: 10K → 50K Users
- [ ] Deploy PgBouncer
- [ ] Redis Cluster (replace single Redis)
- [ ] Qdrant cluster (3→6 nodes)
- [ ] Org-level rate limits
- [ ] Query embedding cache
- [ ] Separate reranker service deployment
- [ ] Partition `usage_metrics` table

### Phase C: 50K → 100K Users
- [ ] PostgreSQL read replicas + query routing
- [ ] LLM gateway with token budgets
- [ ] Semantic answer cache
- [ ] Celery queue priority + backpressure
- [ ] OpenSearch ILM for cold workspaces
- [ ] Multi-AZ with pod disruption budgets
- [ ] Load testing validation (500 QPS sustained)

### Phase D: 100M Chunks
- [ ] Qdrant sharding within large workspaces
- [ ] Background re-index pipeline for model changes
- [ ] Chunk content archival (metadata in PG, content in object store)
- [ ] Approximate search tuning (ef_search vs recall trade-off)
- [ ] Evaluate dedicated vector DB managed service (Pinecone, Weaviate Cloud) for TCO

---

## Failure Modes at Scale

| Failure | Impact | Mitigation |
|---------|--------|------------|
| LLM provider outage | Chat unavailable | Gateway fallback chain |
| Qdrant node loss | Degraded search | Replication factor 2 |
| PostgreSQL connection exhaustion | Full outage | PgBouncer mandatory |
| Redis failure | Rate limits + cache lost | Redis Cluster with failover |
| Celery queue backlog | Upload delays | Backpressure + user notification |
| Single tenant abuse | All users slow | Org circuit breaker |
| Embedding API rate limit | Ingestion stalls | Exponential backoff + GPU local fallback |

---

## Key Metrics to Watch

| Metric | Warning | Critical |
|--------|---------|----------|
| API p95 latency | > 2s | > 5s |
| Retrieval p95 | > 500ms | > 2s |
| LLM p95 | > 3s | > 10s |
| Celery queue depth | > 200 | > 1000 |
| PG connection utilization | > 70% | > 90% |
| Qdrant search p95 | > 80ms | > 200ms |
| Token spend vs budget | > 80% daily | > 100% daily |
| Error rate | > 1% | > 5% |

See [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md) for dashboard and alert definitions.
