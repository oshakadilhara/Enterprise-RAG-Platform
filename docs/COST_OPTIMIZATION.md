# LLM Cost Optimization

Strategy for reducing OpenAI / LLM API spend without degrading answer quality. At the 100K-user baseline (300K queries/day on GPT-4o), unmanaged cost is ~$17.5K/day (~$525K/month). The levers below compound to a **45–70% reduction**.

## Cost Anatomy — Where the Money Goes

Every chat query currently makes **two GPT-4o calls** (query expansion + answer generation), and expansion triples the search load (3 query variants × hybrid search).

Per-query breakdown (GPT-4o at $2.50/1M input, $10/1M output):

| Component | Tokens | Cost/query | % of total |
|-----------|--------|-----------|------------|
| Query expansion (GPT-4o) | ~300 in + 100 out | ~$0.0018 | 3% |
| Main answer: retrieved context (5 chunks) | ~2,500 in | ~$0.0063 | 11% |
| Main answer: chat history | ~1,000 in | ~$0.0025 | 4% |
| Main answer: output | ~500 out | ~$0.0050 | 9% |
| Embedding (3 queries due to expansion) | ~150 | ~$0.000003 | ~0% |
| Infra (retrieval, rerank, storage) amortized | — | ~$0.002 | 3% |
| **All-in per query** | | **~$0.058** | |

**Key insight:** Embeddings are nearly free — the LLM is 99% of the API bill. Optimize LLM usage first; embedding optimization is a distraction until ingestion volume is extreme.

---

## Optimization Levers (Ranked by ROI)

### Tier 1 — Config & Small Code Changes (~45–55% savings, ~1 day of work)

#### 1. Utility model for query expansion
Query expansion is a trivial rewording task — GPT-4o is overkill. Route internal/utility calls to `gpt-4o-mini` (~15× cheaper).

```
# .env addition
LLM_UTILITY_MODEL=gpt-4o-mini
```

Implementation: second LLM provider instance in the service container, used by `RetrievalPipeline._expand_query` and any future internal calls (title generation, classification).

**Direct savings: ~3%.** More importantly, it enables lever #2 and Tier 3 routing.

#### 2. Confidence-gated query expansion
Run vector search with the original query first; only expand when the top score < 0.7 (ambiguous query). ~70% of queries skip expansion entirely.

```
Effect per skipped query:
  - 1 LLM call avoided
  - Hybrid search load drops 3× → 1×
  - ~200ms latency removed
```

**Savings: ~2% LLM cost + ~60% of retrieval infrastructure load.**

#### 3. Prompt-cache-friendly message ordering
OpenAI automatically discounts cached input tokens by **50%**, but only when the static prefix repeats across calls. Message order must place stable content first:

```
✅ CORRECT (cacheable prefix):
   system prompt → chat history → context → question

❌ WRONG (cache broken every query):
   system prompt → context (changes every query) → history → question
```

**Savings: ~15–20% of input cost on multi-turn conversations.** Free — no infrastructure.

#### 4. Token-based history truncation
`chat_history[-6:]` can carry 3,000 tokens of redundant context (6 × 500-token messages). Cap history by **token count (~800)**, not message count.

**Savings: ~5–8%.**

#### 5. Output token cap
Cap `max_tokens` for answers at 1,024 instead of the 4,096 default. Output tokens cost 4× input tokens.

**Savings: ~3–5%.**

---

### Tier 2 — Redis Caching (~15–25% additional)

#### 6. Semantic answer cache
```
Key:  hash(workspace_id + normalized_query + top_chunk_ids)
TTL:  1 hour
Invalidation: any document upload/delete in the workspace
Expected hit rate: 10–15%
```

Each hit skips the **entire LLM call**. At full scale: **~$50K/month saved**.

Trade-off: repeated questions get identical answers for up to 1 hour. Acceptable for knowledge-base queries; invalidation on upload keeps answers fresh.

#### 7. Query embedding cache
```
Key:  SHA256(workspace_id + normalized_query)
TTL:  24 hours
Expected hit rate: 25–35%
```

Saves ~100ms latency per hit; minor cost savings (embeddings are cheap) but free to add alongside #6.

---

### Tier 3 — Architectural (50K+ users)

#### 8. Model routing by query complexity
Classify queries (lookup vs reasoning) and route simple lookups to `gpt-4o-mini`:

```
"What is the vacation policy?"          → gpt-4o-mini (simple lookup)
"Compare clauses 4.2 across contracts"  → gpt-4o     (reasoning)
```

If ~50% of enterprise queries are simple lookups: **up to 40% savings** — the largest single lever.

**Prerequisite:** evaluation harness must be in place first. Run RAGAS faithfulness on both routes weekly; alert on >5% regression. Never deploy model routing without quality measurement.

#### 9. Batch API for ingestion embeddings
OpenAI Batch API gives **50% off** with 24h turnaround. Ingestion is already async (Celery), so latency is acceptable for bulk imports and re-index jobs. Keep the synchronous API for user-triggered uploads.

#### 10. Self-hosted BGE embeddings
Eliminates embedding API cost entirely, but adds GPU infrastructure and ops burden. Only worth it past ~2M new chunks/day. The provider abstraction (`EMBEDDING_PROVIDER=bge`) already supports this — it is an ops decision, not an engineering one.

---

## Combined Savings Projection

| Stage | Monthly Cost (100K users) | Cumulative Reduction |
|-------|--------------------------|---------------------|
| Baseline (unoptimized) | ~$525K | — |
| + Tier 1 (config/code) | ~$265K | ~50% |
| + Tier 2 (caching) | ~$200K | ~62% |
| + Tier 3 (routing) | ~$140K | ~73% |

At smaller scale the percentages hold proportionally — a 1K-user pilot drops from ~$5.3K to ~$1.4K/month.

## Governance Controls (Independent of Optimization)

These don't reduce per-query cost but prevent cost disasters:

| Control | Mechanism |
|---------|-----------|
| Per-org daily token budgets | Redis counter, enforced at LLM gateway |
| Tier limits | Starter 100K / Business 2M / Enterprise 20M tokens/day |
| Org circuit breaker | >3× budget → degrade to retrieval-only responses |
| Anomaly alerts | Org daily cost > 3× its 30-day average |
| Cost dashboard | Daily per-org report (see [Monitoring](MONITORING_OBSERVABILITY.md)) |

## Implementation Order

1. **Sprint 1:** Tier 1 items 1–5 (no new infra, no quality risk)
2. **Sprint 2:** Tier 2 caches (requires Redis key design + invalidation hooks)
3. **Sprint 3+:** Evaluation harness → then Tier 3 model routing
4. **Ongoing:** Governance controls per [Scaling Architecture](SCALING_ARCHITECTURE.md)

Related: [Capacity Planning](CAPACITY_PLANNING.md) for the underlying cost model, [RAG Engineering](RAG_ENGINEERING.md) for the quality trade-offs of context compression.
