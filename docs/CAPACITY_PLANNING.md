# Capacity Planning — 100,000 Users

This document provides the quantitative foundation for infrastructure sizing. All numbers use explicit assumptions so teams can re-calibrate for their workload.

## Assumptions

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Registered users | 100,000 | Design target |
| Daily active users (DAU) | 30% (30,000) | Typical enterprise SaaS |
| Peak concurrent users | 10% of registered (10,000) | Conservative peak factor |
| Queries per DAU per day | 10 | Internal knowledge assistant |
| Documents per organization | 500 avg | Mid-size enterprise |
| Organizations | 5,000 | 100K users / 20 users per org |
| Workspaces per org | 5 avg | Department-level separation |
| Avg document size | 20 pages / 40 chunks | Mixed PDF/DOCX |
| Chunk size | 512 tokens | Current config |
| Embedding dimension | 1536 | OpenAI text-embedding-3-small |

---

## Workload Calculations

### Query Load

```
Daily queries = DAU × queries_per_user
              = 30,000 × 10
              = 300,000 queries/day

Average QPS = 300,000 / 86,400
            = 3.5 QPS

Peak factor (business hours concentration): 50×
Peak QPS = 3.5 × 50
         = ~175 QPS sustained peak

Burst factor (all-hands, incident response): 3×
Burst QPS = 175 × 3
          = ~525 QPS (design for 500 QPS)
```

### Ingestion Load

```
Total documents = orgs × docs_per_org
                = 5,000 × 500
                = 2,500,000 documents

Total chunks = documents × chunks_per_doc
             = 2,500,000 × 40
             = 100,000,000 chunks ✓ (design target)

Daily new uploads (steady state) = 2% of corpus/day
                                 = 50,000 documents/day
                                 = ~2,000,000 new chunks/day

Ingestion throughput required = 50,000 / 86,400
                              = 0.58 docs/sec average
                              = ~3 docs/sec peak
```

### Token Consumption

```
Per query:
  Query expansion:    200 tokens input + 100 output
  Retrieval context:  2,500 tokens input (5 chunks × 500)
  Chat history:       1,000 tokens input (last 6 messages)
  LLM response:       500 tokens output
  ─────────────────────────────────
  Total per query:    ~3,800 input + 600 output

Daily tokens:
  Input:  300,000 × 3,800 = 1.14B tokens/day
  Output: 300,000 × 600   = 180M tokens/day

Monthly tokens:
  Input:  ~34B tokens/month
  Output: ~5.4B tokens/month
```

### Storage

| Store | Calculation | Size |
|-------|-------------|------|
| Raw documents (S3) | 2.5M × 2MB avg | ~5 TB |
| Qdrant vectors | 100M × 1536 dim × 4 bytes | ~600 GB |
| Qdrant payload | 100M × 1KB metadata | ~100 GB |
| Qdrant HNSW index | ~1.5× vector size | ~900 GB |
| OpenSearch | 100M × 2KB (content+metadata) | ~200 GB |
| PostgreSQL metadata | See schema doc | ~120 GB |
| Redis cache | Embedding + semantic cache | ~30 GB |
| **Total** | | **~7 TB** |

---

## Per-Component Sizing

### API Tier

```
Target: 500 QPS burst, 10K concurrent SSE

Per pod capacity (m5.xlarge, 4 workers):
  Non-streaming: ~200 QPS
  SSE streaming: ~500 concurrent connections

Pods required:
  QPS-based: 500 / 200 = 3 pods (CPU bound)
  SSE-based: 10,000 / 500 = 20 pods (connection bound)

Design: 15 pods baseline, HPA to 30
        (SSE is the binding constraint)
```

### Retrieval Tier

```
Per query retrieval cost:
  1× embedding API call (or cache hit)
  1× Qdrant search (50 results)
  1× OpenSearch search (50 results)
  1× rerank (50 → 5 documents)

At 500 QPS peak:
  Qdrant: 500 searches/sec → 12-node cluster
  OpenSearch: 500 searches/sec → 9 data nodes
  Reranker: 500 × 50 pairs = 25,000 pairs/sec
            → 8 dedicated reranker pods (CPU)
  Embedding: 500 calls/sec (75% cache hit → 125 actual)
             → manageable with cache
```

### Worker Tier

```
Document processing time (avg):
  Extract: 5s
  Chunk: 1s
  Embed (40 chunks, batch): 10s
  Index (Qdrant + OS): 5s
  Total: ~21s per document

Peak ingestion (3 docs/sec):
  Workers needed: 3 × 21 = 63 worker-seconds/sec
                  = 63 concurrent workers

Design: 16 CPU workers + 4 GPU workers
  GPU workers handle embedding batching (4× faster)
  Effective capacity: ~8 docs/sec peak
```

### PostgreSQL

```
Connection demand at 100K users:
  API pods: 15 × 4 workers × 10 connections = 600
  Celery workers: 20 × 5 = 100
  Analytics: 50
  Total client demand: ~750 connections

Without PgBouncer: FAILS (RDS max ~500 connections on large instance)
With PgBouncer (transaction mode, pool=100): OK

Instance: db.r6g.2xlarge (8 vCPU, 64GB)
  + 2 read replicas (db.r6g.xlarge)
  IOPS: 12,000 gp3 baseline
```

### Qdrant Cluster

```
100M vectors × 1536 dim:
  Raw vectors: 600 GB
  HNSW graph: ~900 GB
  With replication (×2): ~3 TB total cluster storage

Per node (r6gd.2xlarge, 64GB RAM, 1.9TB NVMe):
  Usable per node: ~50GB vectors (HNSW in RAM for hot collections)
  Nodes for RAM: 3TB / 50GB = 60 nodes (worst case, all hot)

Reality: Workspace access is Pareto-distributed
  Top 20% workspaces = 80% of queries
  Hot cache: ~5TB across 12 nodes handles 100K users
  Cold collections: disk-backed, higher latency acceptable
```

---

## Cost Model (Monthly, AWS us-east-1)

| Component | Spec | Monthly Cost |
|-----------|------|-------------|
| EKS control plane | 1 cluster | $73 |
| API pods | 15 × m5.xlarge | $2,750 |
| Worker pods | 16 CPU + 4 GPU | $4,200 |
| RDS PostgreSQL | r6g.2xlarge Multi-AZ + 2 RR | $1,800 |
| ElastiCache Redis | 6 × r6g.large cluster | $1,200 |
| Qdrant (self-hosted EKS) | 12 × r6gd.2xlarge | $3,600 |
| OpenSearch | 9 × r6g.2xlarge.search | $2,700 |
| S3 | 5 TB + requests | $120 |
| CloudFront | 2 TB transfer | $170 |
| CloudWatch / monitoring | Logs + metrics | $300 |
| **Infrastructure subtotal** | | **~$16,900** |
| LLM API (GPT-4o, 300K queries/day) | See scaling doc | **~$375,000** |
| Embedding API | 2M new chunks/day | **~$8,000** |
| **Total** | | **~$400,000/month** |

### Cost Optimization Levers

| Lever | Savings | Trade-off |
|-------|---------|-----------|
| Semantic answer cache (15% hit) | ~$56K/month LLM | Stale answers for repeated queries |
| GPT-4o-mini for query expansion | ~$20K/month | Slightly worse expansion |
| Self-hosted BGE embeddings | ~$8K/month | GPU infra cost, ops burden |
| Context compression (summarize chunks) | ~$50K/month | Potential recall loss |
| Bedrock reserved throughput | ~15% on LLM | Vendor lock-in |
| Tiered org limits | Variable | User experience for heavy users |

---

## Load Testing Requirements

Before declaring 100K readiness, execute these tests:

| Test | Target | Tool |
|------|--------|------|
| Sustained query load | 100 QPS for 1 hour, p95 < 3s | Locust / k6 |
| Burst query load | 500 QPS for 5 min, error < 1% | k6 |
| Concurrent SSE | 10,000 streams for 30 min | Custom script |
| Ingestion throughput | 5 docs/sec for 1 hour | Celery load test |
| Failover: kill 1 Qdrant node | p95 increase < 50% | Chaos Mesh |
| Failover: kill 1 API pod | Zero user-visible errors | K8s pod delete |
| DB connection storm | 1000 concurrent API pods | Connection test |

---

## Growth Triggers — When to Scale

| Signal | Threshold | Action |
|--------|-----------|--------|
| API p95 latency | > 2s for 15 min | +3 API pods |
| Celery queue depth | > 200 for 10 min | +4 workers |
| PG CPU | > 70% sustained | Upgrade instance or add replica |
| Qdrant p95 search | > 80ms | +2 nodes or tune ef_search |
| LLM error rate | > 2% | Enable fallback provider |
| Monthly LLM cost | > 120% budget | Enable semantic cache + tier limits |
| Disk usage (Qdrant) | > 75% | Add nodes or ILM cold tier |

---

## Sizing Calculator

Use these formulas to re-size for your actual workload:

```python
# Inputs
users = 100_000
dau_rate = 0.30
queries_per_dau = 10
peak_factor = 50
docs_per_org = 500
orgs = users // 20
chunks_per_doc = 40

# Outputs
daily_queries = users * dau_rate * queries_per_dau
avg_qps = daily_queries / 86400
peak_qps = avg_qps * peak_factor
total_chunks = orgs * docs_per_org * chunks_per_doc
api_pods = max(peak_qps / 200, (users * 0.10) / 500)
qdrant_nodes = max(3, total_chunks // 8_000_000)  # ~8M vectors per node
monthly_llm_cost_usd = daily_queries * 30 * 0.058  # ~$0.058 per query all-in
```

See [SCALING_ARCHITECTURE.md](SCALING_ARCHITECTURE.md) for architectural responses to these numbers.
