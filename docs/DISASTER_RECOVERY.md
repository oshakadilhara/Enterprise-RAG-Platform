# Disaster Recovery & Business Continuity

Recovery procedures for the Enterprise RAG Platform. Target: **99.9% availability** (8.7 hours downtime/year) with **RPO < 1 hour** and **RTO < 30 minutes** for critical services.

## Recovery Objectives

| Tier | Service | RPO | RTO | Priority |
|------|---------|-----|-----|----------|
| 1 | API + Chat (read path) | 0 | 15 min | Highest |
| 1 | Authentication | 0 | 15 min | Highest |
| 2 | Document ingestion | 1 hour | 30 min | High |
| 2 | Retrieval (Qdrant + OS) | 1 hour | 30 min | High |
| 3 | Analytics / evaluation | 24 hours | 4 hours | Medium |
| 3 | Audit logs | 0 | 1 hour | Medium (compliance) |

---

## Failure Scenarios

### Scenario 1: Single AZ Failure

**Impact:** 33% capacity loss in 3-AZ setup.
**Detection:** Kubernetes node NotReady, ALB unhealthy targets.
**Recovery:** Automatic — K8s reschedules pods to healthy AZs.
**RTO:** 2–5 minutes (pod rescheduling).
**Action required:** None (verify pod redistribution).

### Scenario 2: Regional Failure (us-east-1 Down)

**Impact:** Full platform unavailable.
**Detection:** All health checks fail, Route 53 failover triggers.
**Recovery:** DNS failover to us-west-2 DR cluster.
**RTO:** 15–30 minutes (DNS propagation + warm standby activation).

```
Route 53 Health Check (us-east-1 ALB)
  ├── Healthy → route to us-east-1
  └── Unhealthy (3 failures) → failover to us-west-2
```

### Scenario 3: PostgreSQL Primary Failure

**Impact:** All writes fail, reads may continue on replicas.
**Detection:** RDS failover event, connection errors in API logs.
**Recovery:** Automatic RDS Multi-AZ failover to standby.
**RTO:** 60–120 seconds (automatic).
**Post-recovery:** Verify PgBouncer reconnection, check for in-flight transaction loss.

### Scenario 4: Qdrant Cluster Corruption

**Impact:** Vector search unavailable, chat returns no results.
**Detection:** Search errors in retrieval pipeline, Qdrant health check fails.
**Recovery:**
1. Route traffic to OpenSearch-only (BM25 fallback, degraded mode)
2. Restore Qdrant from latest snapshot
3. Run reconciliation job to verify vector count matches PostgreSQL
**RTO:** 30 minutes (snapshot restore).
**Degraded mode:** Chat works with reduced recall (BM25 only, no semantic search).

### Scenario 5: LLM Provider Global Outage

**Impact:** Chat generation fails, ingestion query expansion fails.
**Detection:** LLM error rate > 50%, provider status page.
**Recovery:**
1. LLM gateway auto-failover to secondary provider
2. If all providers down: return retrieved context without generation
3. Disable query expansion (use original query only)
**RTO:** 1–5 minutes (automatic failover).
**Degraded mode:** "Here are the relevant document excerpts:" without LLM synthesis.

### Scenario 6: Redis Cluster Failure

**Impact:** Rate limiting lost, cache misses, Celery broker down.
**Detection:** Redis connection errors, Celery workers idle.
**Recovery:**
1. ElastiCache automatic failover to replica
2. Celery reconnects automatically
3. Cache rebuilds on demand (no data loss, performance impact only)
**RTO:** 30–60 seconds (automatic).

---

## Backup Strategy

| Data Store | Method | Frequency | Retention | Recovery Test |
|------------|--------|-----------|-----------|---------------|
| PostgreSQL | RDS automated snapshots | Daily | 35 days | Monthly |
| PostgreSQL | Manual snapshot before migrations | Per migration | 90 days | Per migration |
| Qdrant | Volume snapshots (EBS) | Daily | 14 days | Quarterly |
| OpenSearch | Automated snapshots to S3 | Daily | 30 days | Quarterly |
| S3 documents | Cross-region replication | Continuous | Indefinite | Quarterly |
| Redis | AOF persistence | Continuous | 7 days | Monthly |
| Secrets | Secrets Manager versioning | Per rotation | 30 versions | Per rotation |

### Backup Verification

```bash
# Monthly: Restore PostgreSQL snapshot to test instance
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier rag-test-restore \
  --db-snapshot-identifier rag-prod-snapshot-latest

# Verify row counts match production metadata
psql -c "SELECT count(*) FROM documents;"
psql -c "SELECT count(*) FROM document_chunks;"

# Quarterly: Restore Qdrant snapshot, verify search works
# Quarterly: Restore OpenSearch snapshot, verify BM25 search works
```

---

## Multi-Region Architecture

### Active-Passive (Recommended for 100K Users)

```
us-east-1 (PRIMARY)                    us-west-2 (DR)
├── EKS Cluster (15 API, 16 workers)   ├── EKS Cluster (5 API, 4 workers)
├── RDS Primary (Multi-AZ)             ├── RDS Read Replica (promotable)
├── ElastiCache Primary                ├── ElastiCache (standby)
├── Qdrant Cluster (12 nodes)          ├── Qdrant (async replication)
├── OpenSearch (9 nodes)               ├── OpenSearch (replica)
├── S3 (primary bucket)                ├── S3 (CRR destination)
└── Route 53 (active)                  └── Route 53 (failover, idle)
```

### Data Replication

| Store | Replication Method | Lag | Failover |
|-------|-------------------|-----|----------|
| PostgreSQL | RDS cross-region read replica | < 1s | Promote replica (manual, 5 min) |
| S3 | Cross-Region Replication | < 15 min | Automatic (DNS switch) |
| Qdrant | Snapshot sync (hourly) | < 1 hour | Restore from snapshot |
| OpenSearch | Cross-cluster replication | < 5s | Manual alias switch |
| Redis | Not replicated (cache) | N/A | Rebuild on demand |

**Critical:** PostgreSQL is the source of truth. All other stores can be rebuilt from PostgreSQL metadata + S3 raw files, given sufficient time.

### Full Rebuild Procedure (Worst Case)

If all search indexes are lost but PostgreSQL and S3 survive:

```
1. Provision new Qdrant + OpenSearch clusters     [30 min]
2. Query PostgreSQL for all completed documents    [5 min]
3. Queue re-index Celery jobs (low priority)       [immediate]
4. Process at 5 docs/sec = 2.5M docs in ~6 days  [background]
5. Chat available with degraded search immediately  [BM25 only from OpenSearch rebuild]
6. Full hybrid search restored as re-index completes [progressive]
```

---

## Failover Runbook

### Regional Failover (Manual Decision)

**Trigger criteria:**
- Primary region unavailable > 10 minutes
- AWS status page confirms regional issue
- Engineering Lead approves failover

**Procedure:**
```bash
# 1. Promote DR database
aws rds promote-read-replica \
  --db-instance-identifier rag-dr-replica \
  --region us-west-2

# 2. Update Route 53 failover
aws route53 change-resource-record-sets \
  --hosted-zone-id ZONE_ID \
  --change-batch file://failover-to-dr.json

# 3. Scale DR cluster
kubectl scale deployment rag-backend --replicas=15 -n rag-platform \
  --context dr-cluster

# 4. Update ConfigMap with DR endpoints
kubectl apply -f infrastructure/kubernetes/configmap-dr.yaml

# 5. Verify
curl https://api.rag.example.com/health
# Run synthetic chat query

# 6. Communicate
# Status page: "Failover to DR region in progress"
# Internal: Slack #incidents
```

**Failback:** When primary region recovers, reverse the process during next maintenance window. Do not failback under load.

---

## Degraded Mode Operations

The platform supports graceful degradation — partial service is better than no service.

| Degradation Level | What's Available | What's Disabled | Trigger |
|-------------------|-----------------|--------------|---------|
| Level 0 (Normal) | Everything | Nothing | — |
| Level 1 | Chat (slower), upload | Query expansion | LLM provider slow |
| Level 2 | Chat (BM25 only), upload | Vector search, reranking | Qdrant down |
| Level 3 | Document search only | Chat generation | All LLM providers down |
| Level 4 | Read-only (existing data) | Upload, chat | PostgreSQL primary down |
| Level 5 | Maintenance page | Everything | Full regional failure (during failover) |

**Automatic degradation triggers:**
```python
if qdrant_health.is_down():
    retrieval_config.vector_search_enabled = False
    retrieval_config.bm25_weight = 1.0

if all_llm_providers_down():
    chat_config.generation_enabled = False
    chat_config.return_context_only = True
```

---

## DR Testing Schedule

| Test | Frequency | Duration | Impact |
|------|-----------|----------|--------|
| Pod kill chaos | Monthly | 30 min | None (resilience verify) |
| Database failover | Quarterly | 1 hour | 2 min read-only blip |
| Redis failover | Quarterly | 30 min | Brief cache miss spike |
| Regional failover (tabletop) | Semi-annual | 4 hours | None (paper exercise) |
| Regional failover (live) | Annual | 4 hours | Controlled user impact |
| Full rebuild from backup | Annual | 8 hours | DR environment only |

Document results of every DR test. Update this runbook with lessons learned.

---

## Business Continuity Contacts

| Role | Responsibility During DR |
|------|-------------------------|
| Incident Commander | Decision to failover, communication |
| Platform SRE | Execute failover runbook |
| Backend Engineer | Verify application health post-failover |
| DBA | Database promotion and verification |
| Customer Success | Tenant communication |
| Legal/Compliance | Breach notification if data affected |
