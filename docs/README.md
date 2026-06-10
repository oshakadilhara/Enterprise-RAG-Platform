# Enterprise RAG Platform — Documentation Hub

Complete technical documentation for designing, operating, and scaling the platform to **100,000 users** and **100 million chunks**.

## Start Here

| Audience | Document | Purpose |
|----------|----------|---------|
| Everyone | [Architecture Overview](ARCHITECTURE.md) | System design and layer boundaries |
| Platform / SRE | [Scaling Architecture](SCALING_ARCHITECTURE.md) | How we scale to 100K users |
| Platform / FinOps | [Capacity Planning](CAPACITY_PLANNING.md) | Sizing, throughput math, cost models |
| ML / Retrieval | [RAG Engineering Guide](RAG_ENGINEERING.md) | Retrieval pipeline at enterprise scale |
| ML / FinOps | [Cost Optimization](COST_OPTIMIZATION.md) | Reducing LLM API spend 45–70% |
| ML / Compliance | [Explainable AI](EXPLAINABLE_AI.md) | Citations, traceability, abstention |
| Backend | [API Contracts](API_CONTRACTS.md) | REST API reference |
| Backend | [Database Schema](DATABASE_SCHEMA.md) | Tables, indexes, vector index design |
| DevOps | [Deployment Guide](DEPLOYMENT_GUIDE.md) | Production rollout steps |
| DevOps | [AWS Architecture](AWS_ARCHITECTURE.md) | Cloud-native deployment on EKS |
| SRE | [Operations Runbook](OPERATIONS_RUNBOOK.md) | Incident response and daily ops |
| SRE | [Monitoring & Observability](MONITORING_OBSERVABILITY.md) | Metrics, alerts, SLOs |
| Security | [Security & Compliance](SECURITY_COMPLIANCE.md) | Auth, tenancy isolation, audit |
| SRE | [Disaster Recovery](DISASTER_RECOVERY.md) | Backup, failover, multi-region |
| Product / Eng | [Development Roadmap](ROADMAP.md) | Phased delivery plan |

## Scaling Documentation (100K Users)

These documents are written for senior engineers making production decisions — not as implementation checklists.

```
                    ┌─────────────────────────────┐
                    │   CAPACITY_PLANNING.md      │
                    │   Load profiles, QPS, cost  │
                    └──────────────┬──────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ SCALING_         │   │ RAG_ENGINEERING  │   │ MULTI_TENANCY    │
│ ARCHITECTURE     │   │ Guide            │   │ Isolation        │
│ Horizontal scale │   │ 100M chunks      │   │ Noisy neighbors  │
└────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘
         │                      │                      │
         └──────────────────────┼──────────────────────┘
                                ▼
              ┌─────────────────────────────────────┐
              │  MONITORING │ RUNBOOK │ DR │ SECURITY │
              └─────────────────────────────────────┘
```

## Design Targets

| Dimension | Target | Document |
|-----------|--------|----------|
| Registered users | 100,000 | [Capacity Planning](CAPACITY_PLANNING.md) |
| Peak concurrent users | 10,000 (10%) | [Scaling Architecture](SCALING_ARCHITECTURE.md) |
| Document chunks | 100,000,000 | [RAG Engineering](RAG_ENGINEERING.md) |
| Peak query throughput | 500 QPS | [Capacity Planning](CAPACITY_PLANNING.md) |
| P95 chat latency | < 3 seconds | [Monitoring](MONITORING_OBSERVABILITY.md) |
| Availability | 99.9% (8.7h downtime/yr) | [Disaster Recovery](DISASTER_RECOVERY.md) |
| Retrieval precision@5 | > 0.85 | [RAG Engineering](RAG_ENGINEERING.md) |

## Document Conventions

- **Assumptions** are stated explicitly with formulas
- **Bottlenecks** are identified per component with mitigation
- **Trade-offs** are documented (cost vs latency vs quality)
- **Phased rollout** paths are provided (10K → 50K → 100K)

## Quick Reference: Critical Scaling Decisions

1. **Workspace-scoped indexes** — Never search 100M chunks globally; always filter by `workspace_id`
2. **Async ingestion** — Upload path must never block on embedding; Celery queue with backpressure
3. **Two-tier caching** — Redis for query embeddings + semantic answer cache (org-scoped TTL)
4. **Reranker on CPU workers** — GPU pool for batch ingestion; CPU autoscaled pool for online rerank
5. **PgBouncer** — Mandatory at 100K users; PostgreSQL connection exhaustion is the #1 outage cause
6. **Per-tenant rate limits** — IP-level limits are insufficient; enforce at org + user level
7. **LLM gateway** — Centralized provider routing with token budgets and circuit breakers
8. **Utility model for internal calls** — Query expansion on gpt-4o-mini, not GPT-4o (see [Cost Optimization](COST_OPTIMIZATION.md))
9. **Abstain on low confidence** — An honest "I don't know" beats a hallucination (see [Explainable AI](EXPLAINABLE_AI.md))
