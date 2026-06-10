# RAG Engineering Guide — Enterprise Scale

Senior retrieval engineering reference for operating hybrid RAG at 100M chunks and 300K+ daily queries. This is not a tutorial — it is a production decision framework.

## The Retrieval Problem at Scale

At 100M chunks, RAG stops being "embed and search" and becomes a **distributed information retrieval system** with ML components. The failure modes are different:

| Small Scale (<1M chunks) | Enterprise Scale (100M chunks) |
|--------------------------|-------------------------------|
| Global search is fast enough | Global search is prohibitive |
| One embedding model fits all | Model changes require re-index campaigns |
| Hybrid search always helps | Bad fusion weights amplify noise |
| Reranking is optional | Reranking is mandatory for precision |
| Latency is dominated by LLM | Retrieval can equal or exceed LLM time |

---

## Index Architecture

### Workspace Partitioning (Non-Negotiable)

```
❌ WRONG: Single collection with 100M vectors + workspace_id filter
✅ RIGHT: Collection per workspace, search scoped before query execution
```

**Why:** HNSW graph traversal on 100M vectors takes 200–500ms even with filters. On 50K vectors per workspace: 20–50ms.

**Large workspace handling (>500K chunks):**

```
workspace_{id}                    # routing alias
  ├── workspace_{id}_shard_0     # chunks 0–500K
  ├── workspace_{id}_shard_1     # chunks 500K–1M
  └── workspace_{id}_shard_N
```

Search all shards in parallel, merge top-K. Add shards when workspace exceeds 500K chunks.

### Dual-Index Consistency

Every chunk exists in **two stores** that must stay synchronized:

| Store | Purpose | Consistency |
|-------|---------|-------------|
| Qdrant | Semantic similarity | Eventual (seconds) |
| OpenSearch | Lexical/BM25 match | Eventual (seconds) |
| PostgreSQL | Metadata, lineage | Strong |

**Write protocol:**
```
1. Write to PostgreSQL (status: processing)
2. Embed batch
3. Upsert Qdrant (with vector_id)
4. Index OpenSearch (with opensearch_id)
5. Update PostgreSQL (status: completed, store both IDs)
```

**Delete protocol:**
```
1. Delete from Qdrant (by document_id filter)
2. Delete from OpenSearch (by document_id term query)
3. Delete chunks from PostgreSQL
4. Delete raw file from S3
5. Invalidate workspace cache
```

**Failure recovery:** If step 3 or 4 fails, document stays in `failed` state. Reconciliation job runs every 15 minutes to detect orphaned vectors (in Qdrant but not in PG) and ghost entries (in PG but not in indexes).

---

## Chunking Strategy Selection

| Strategy | Best For | Chunks/Doc (20pg) | Retrieval Quality | Ingestion Cost |
|----------|----------|-------------------|-------------------|----------------|
| Fixed | Uniform text, CSV | ~80 | Medium | Low |
| Recursive | General documents | ~40 | High | Low |
| Semantic | Policy/legal docs | ~25 | Highest | Medium |

**Enterprise recommendation:** Default `recursive` with `chunk_size=512`, `overlap=64`. Allow per-workspace override for legal/compliance workspaces (semantic, smaller chunks).

**Chunk size trade-off at scale:**

```
Smaller chunks (256):
  + Higher precision per chunk
  - 2× more vectors → 2× storage, 2× ingestion cost
  - More reranker pairs per query

Larger chunks (1024):
  + Fewer vectors, lower cost
  - Context pollution in LLM prompt
  - Lower precision for specific fact retrieval

Sweet spot: 512 tokens with 64 overlap (current default)
```

### Chunk Metadata (Required Fields)

Every chunk must carry these fields in both Qdrant payload and OpenSearch document:

```json
{
  "chunk_id": "uuid",
  "document_id": "uuid",
  "workspace_id": "uuid",
  "file_name": "policy.pdf",
  "page_number": 12,
  "chunk_index": 5,
  "upload_date": "2026-06-10T00:00:00Z",
  "content": "..."
}
```

Missing `workspace_id` in payload = security vulnerability at scale (cross-tenant leakage in misconfigured queries).

---

## Hybrid Search Fusion

### Current: Weighted Linear Combination

```
final_score = 0.6 × norm(vector_score) + 0.4 × norm(bm25_score)
```

**Score normalization:** Min-max per query batch. Without normalization, BM25 scores (unbounded) dominate vector scores (0–1 cosine).

### When to Adjust Weights

| Query Type | Vector Weight | BM25 Weight | Example |
|------------|--------------|-------------|---------|
| Conceptual | 0.8 | 0.2 | "What is our remote work philosophy?" |
| Exact match | 0.3 | 0.7 | "Section 4.2.1 termination clause" |
| Mixed (default) | 0.6 | 0.4 | "What is the vacation policy?" |
| Code/IDs | 0.2 | 0.8 | "Error code AUTH-401" |

**At 100K scale:** Implement query classification (rule-based or lightweight classifier) to dynamically adjust weights. A 5–10% precision improvement is worth the complexity at 300K queries/day.

### Reciprocal Rank Fusion (RRF) — Upgrade Path

For Phase C (50K+ users), consider RRF as a more robust fusion method:

```
RRF_score(d) = Σ 1 / (k + rank_i(d))    for each retrieval method i
k = 60 (standard constant)
```

RRF is rank-based, not score-based — eliminates normalization problems. Trade-off: slightly higher compute, better fusion stability across heterogeneous score distributions.

---

## Reranking at Scale

### Why Reranking is Mandatory

Hybrid search top-50 at 100M chunks has ~70% recall@50 but only ~55% precision@5. Reranking closes this gap to ~85% precision@5.

### Architecture

```
Online reranking (per query):
  Input: 50 (query, chunk) pairs
  Model: BGE-reranker-v2-m3 (CPU) or ms-marco-MiniLM (faster)
  Output: Top 5
  Latency: 100–300ms on CPU

Offline reranking (evaluation only):
  Input: Full dataset
  Model: Larger cross-encoder
  Purpose: Quality benchmarking, weight tuning
```

### Scaling Reranker Throughput

At 500 QPS × 50 pairs = 25,000 inference pairs/second.

| Approach | Throughput | Latency | Cost |
|----------|-----------|---------|------|
| In-process (current) | ~10 QPS/pod | 300ms | Low |
| Dedicated service (8 pods) | ~400 QPS | 250ms | Medium |
| GPU batching (2× T4) | ~1000 QPS | 100ms | Higher |
| Cascade: mini → full | ~500 QPS | 150ms | Optimal |

**Recommended cascade at 100K users:**
1. Mini cross-encoder: 50 → 15 (fast, cheap)
2. Full BGE reranker: 15 → 5 (precise)

This cuts rerank latency by ~40% with <2% precision loss.

---

## Query Expansion — Cost Control

Query expansion uses an LLM call per query. At 300K queries/day, this is expensive.

**Strategies by scale:**

| Scale | Strategy |
|-------|----------|
| <10K users | LLM expansion (2 alternatives) |
| 10K–50K users | LLM expansion with cache |
| 50K–100K users | HyDE only for low-confidence queries |
| 100K+ users | Rule-based expansion + LLM for 10% of queries |

**HyDE (Hypothetical Document Embedding):**
Generate a hypothetical answer, embed it, search with that vector. Better for conceptual queries, single embedding call instead of multiple searches.

**Confidence gate:**
```
if top_vector_score < 0.7:
    run query expansion (likely ambiguous query)
else:
    skip expansion (save 200ms + LLM cost)
```

---

## Embedding Model Strategy

### Model Selection Matrix

| Model | Dimension | Quality | Cost (1M tokens) | Latency |
|-------|-----------|---------|-------------------|---------|
| text-embedding-3-small | 1536 | High | $0.02 | 50ms API |
| text-embedding-3-large | 3072 | Highest | $0.13 | 80ms API |
| BGE-large-en-v1.5 | 1024 | High | Self-hosted | 20ms GPU |
| Titan Embed v2 | 1024 | High | $0.02 | 40ms Bedrock |

### Model Change Protocol

Changing embedding models at 100M chunks is a **multi-week project**, not a config change:

```
Week 1: Deploy new collections with suffix _v2
Week 2-4: Background re-index (Celery low-priority queue)
Week 4: A/B test retrieval quality (10% traffic to v2)
Week 5: Cutover alias, deprecate v1
Week 6: Delete v1 collections
```

Never change embedding model in-place. Always blue/green.

---

## Context Building for LLM

### Token Budget Allocation (8K context window)

| Component | Tokens | Notes |
|-----------|--------|-------|
| System prompt | 200 | Fixed |
| Chat history | 1,000 | Last 6 messages, truncated |
| Retrieved context | 2,500 | 5 chunks × 500 tokens |
| User query | 100 | |
| Generation reserve | 4,200 | For response |
| **Total** | **8,000** | |

### Context Quality Rules

1. **Deduplicate** — If two chunks from same page overlap >80%, keep higher-scored only
2. **Order by relevance** — Highest rerank score first (LLM attention bias to early context)
3. **Include source headers** — `[Source: filename, Page X]` before each chunk
4. **Truncate, don't split** — Cut at sentence boundary, not mid-word
5. **Max 5 chunks** — Beyond 5, LLM confusion increases faster than recall improves

---

## Evaluation at Scale

### Offline Evaluation Pipeline

```
Weekly automated eval:
  1. Sample 100 queries per active workspace (stratified)
  2. Run retrieval pipeline (no LLM)
  3. Measure: precision@5, recall@50, MRR, NDCG
  4. Run RAGAS faithfulness on 20 query-answer pairs
  5. Alert if any metric drops >5% week-over-week
```

### Online Quality Signals

| Signal | Detection | Action |
|--------|-----------|--------|
| Low rerank scores (all <0.3) | No relevant docs found | Return "I don't have information" |
| User rephrase (same conv, similar query) | Retrieval miss | Log for eval dataset |
| Thumbs down (future) | Answer quality issue | Feed into eval pipeline |
| High latency + low score | Index health issue | Alert on-call |

### Metrics Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Precision@5 | > 0.85 | Offline weekly |
| Recall@50 | > 0.90 | Offline weekly |
| MRR | > 0.80 | Offline weekly |
| Faithfulness | > 0.90 | RAGAS monthly |
| Answer relevancy | > 0.85 | RAGAS monthly |
| Context precision | > 0.80 | RAGAS monthly |
| Retrieval p95 | < 500ms | Prometheus realtime |

---

## Anti-Patterns at Enterprise Scale

| Anti-Pattern | Why It Fails | Alternative |
|-------------|-------------|-------------|
| Single global vector index | 500ms+ search at 100M | Workspace partitioning |
| Synchronous ingestion | Blocks API, timeouts | Celery async queue |
| No reranking | 55% precision@5 | Cascade reranker |
| Same LLM for expansion + answer | 2× cost, 2× latency | Cache + confidence gate |
| Storing chunk content in PostgreSQL | 100M rows of TEXT kills PG | Content in vector/search stores only |
| IP-only rate limiting | One org can exhaust capacity | Org + user limits |
| Re-index in production hours | Degrades live search | Background low-priority queue |
| Ignoring embedding model versioning | Silent quality regression | Blue/green collections |

---

## Retrieval Latency Budget

```
┌─────────────────────────────────────────────────────────┐
│                  3000ms total (p95 target)               │
├──────────────┬──────────────┬────────────┬─────────────┤
│ Embed/cache  │ Hybrid search│  Rerank    │ LLM stream  │
│   150ms      │    200ms     │   300ms    │   2000ms    │
│   (5%)       │    (7%)      │   (10%)    │   (67%)     │
│              │              │            │  first token  │
│              │              │            │  at ~800ms    │
└──────────────┴──────────────┴────────────┴─────────────┘
```

LLM dominates latency. Optimize retrieval first (it is cheaper and under your control), then attack LLM cost with caching and model routing.

See [SCALING_ARCHITECTURE.md](SCALING_ARCHITECTURE.md) for infrastructure responses and [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md) for per-stage metrics.
