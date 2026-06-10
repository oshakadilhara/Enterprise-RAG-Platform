# Explainable AI (XAI) for Enterprise RAG

How the platform makes AI answers transparent, verifiable, and auditable. Explainability is a trust and compliance requirement for enterprise AI — not a nice-to-have.

## Why RAG is "Explainable by Architecture"

A fine-tuned LLM's answer is a black box — there is no way to trace why it said what it said. RAG inverts this: the **explanation artifact already exists** — the retrieved chunks, their scores, and the pipeline trace. The engineering question is how much of that evidence we surface, persist, and verify.

The platform already captures more than it exposes. Every `SearchResult` carries the full score breakdown:

| Field | Meaning |
|-------|---------|
| `vector_score` | Semantic similarity (embedding cosine) |
| `bm25_score` | Keyword/lexical match strength |
| `hybrid_score` | Weighted fusion (0.6 vector + 0.4 BM25) |
| `rerank_score` | Cross-encoder relevance (final ranking) |

And `RetrievalContext` carries `expanded_queries` and per-stage latency. Today, the `Citation` schema collapses all of this into a single `relevance_score`, and the retrieval trace is discarded after the response. Closing that gap is the XAI roadmap.

---

## The Four Levels of RAG Explainability

| Level | Question Answered | Platform Status |
|-------|-------------------|-----------------|
| **1. Answer attribution** | "Where did this answer come from?" | ✅ Citations: file, page, snippet, score |
| **2. Retrieval reasoning** | "Why were these sources chosen?" | ⚠️ Scores captured internally, not exposed |
| **3. Claim verification** | "Is each sentence actually supported?" | ❌ Offline only (RAGAS faithfulness) |
| **4. Decision traceability** | "Can we audit this answer in 6 months?" | ⚠️ Citations persisted; full trace is not |

**Why Level 4 matters:** under the EU AI Act and for legal/HR use cases, "the AI told an employee X about their termination rights" must be reconstructible — which model, which document version, which chunks, what scores, what prompt. This is an audit requirement, not a UX feature.

---

## XAI Feature Roadmap

### Tier 1 — Expose What Already Exists (low effort, cost-neutral)

#### 1. Score breakdown in citations
Extend the `Citation` schema:

```json
{
  "document_id": "uuid",
  "file_name": "hr-policy.pdf",
  "page_number": 12,
  "content_snippet": "...",
  "vector_score": 0.82,
  "bm25_score": 0.45,
  "rerank_score": 0.91,
  "match_type": "semantic"  // semantic | keyword | both
}
```

The UI shows *why* each source surfaced ("strong semantic match" vs "exact keyword match"). Cheapest trust win available.

#### 2. Confidence scoring and abstention
If the top rerank score falls below a threshold (~0.3), do not generate a confident answer. Return:

> "I couldn't find sufficient information in this workspace to answer reliably."

…optionally listing the weak candidates found. **An honest "I don't know" is the most important explainability feature** — it calibrates user trust and eliminates the worst hallucination cases. Configuration:

```
RETRIEVAL_CONFIDENCE_THRESHOLD=0.3
ABSTAIN_ON_LOW_CONFIDENCE=true
```

#### 3. Persisted retrieval trace
Store the full pipeline trace alongside each assistant message:

```json
{
  "expanded_queries": ["original", "variant 1", "variant 2"],
  "stage_latencies_ms": {"expansion": 120, "hybrid": 180, "rerank": 250},
  "candidates_considered": 50,
  "model": "gpt-4o",
  "embedding_model": "text-embedding-3-small",
  "chunk_scores": [{"chunk_id": "...", "rerank_score": 0.91}, ...]
}
```

This is the audit backbone for compliance, the debugging tool for support tickets, and a free source of evaluation data.

### Tier 2 — Verification (medium effort)

#### 4. Sentence-level attribution
Post-process the generated answer: map each sentence to its supporting chunk (embedding similarity or a lightweight NLI model). UI renders per-sentence citation markers like academic footnotes. **Unsupported sentences are flagged** — this is online faithfulness checking, versus the current offline-only RAGAS runs.

#### 5. Span highlighting in source documents
When a user clicks a citation, show the source page with the exact supporting span highlighted — not just a 200-character snippet. Requires storing chunk character offsets at ingestion time.

### Tier 3 — Systematic (higher effort)

#### 6. Production faithfulness sampling
Score faithfulness on a sample (~5%) of live answers using a cheap model, feeding the monitoring dashboards. Turns explainability into a measurable SLO:

```
SLO: % of answers fully grounded in retrieved context > 95%
```

#### 7. Contrastive explanations (admin tooling)
"Document Y ranked #6 and was excluded because its rerank score was 0.41 vs the 0.55 cutoff." This answers the #1 future support ticket category: *"Why didn't the AI use my document?"*

---

## Cost Trade-Off

Sentence-level attribution and online faithfulness checks add an extra model call per answer — which pulls against [cost optimization](COST_OPTIMIZATION.md). Reconciliation:

- Use a small/cheap model (gpt-4o-mini or a local NLI model) for verification
- Sample (5–10%) rather than verify 100% of traffic
- **Tier 1 features are cost-neutral** — they expose data the pipeline already computes

## Compliance Mapping

| Requirement | XAI Feature |
|-------------|-------------|
| EU AI Act transparency | Citations + persisted retrieval trace |
| Right to explanation | Score breakdown + trace reconstruction |
| Audit reconstruction | Trace includes model versions + chunk IDs |
| Hallucination risk management | Abstention + faithfulness sampling |
| Human oversight | Admin contrastive explanations |

## Implementation Order

1. **Sprint 1 (Tier 1):** Citation score breakdown, abstention threshold, persisted retrieval trace
2. **Sprint 2 (Tier 2):** Sentence-level attribution, span highlighting
3. **Sprint 3 (Tier 3):** Production faithfulness sampling → XAI SLO on dashboards
4. **Later:** Contrastive explanations as admin tooling

Related: [RAG Engineering](RAG_ENGINEERING.md) for evaluation metrics, [Security & Compliance](SECURITY_COMPLIANCE.md) for audit requirements, [Monitoring](MONITORING_OBSERVABILITY.md) for SLO integration.
