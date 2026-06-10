# Operations Runbook

Incident response and daily operations for the Enterprise RAG Platform at 100K-user scale. Every procedure assumes multi-region, multi-tenant production.

## On-Call Rotation

| Role | Responsibility | Escalation |
|------|---------------|------------|
| L1 — Platform SRE | Infrastructure alerts, pod scaling | 15 min → L2 |
| L2 — Backend Engineer | Application errors, pipeline failures | 30 min → L3 |
| L3 — AI/ML Engineer | Retrieval quality, model issues | 1 hour → Engineering Lead |
| Security | Data isolation, auth breaches | Immediate |

---

## Incident Response Procedures

### P1: API Completely Down

**Symptoms:** Health check failing, 502/503 from ALB, users cannot access platform.

**Diagnosis:**
```bash
# 1. Check pod status
kubectl get pods -n rag-platform -l app=rag-backend

# 2. Check recent events
kubectl get events -n rag-platform --sort-by='.lastTimestamp' | head -20

# 3. Check logs
kubectl logs -l app=rag-backend -n rag-platform --tail=50

# 4. Check database connectivity
kubectl exec -it deploy/rag-backend -n rag-platform -- \
  python -c "from app.core.database import engine; print('DB OK')"
```

**Resolution paths:**

| Root Cause | Fix | ETA |
|------------|-----|-----|
| All pods OOMKilled | Increase memory limit, redeploy | 5 min |
| PostgreSQL down | Failover to replica, check RDS | 10 min |
| Bad deployment | `kubectl rollout undo deployment/rag-backend` | 3 min |
| Redis down | Failover to replica node | 5 min |
| Certificate expired | Renew cert, reload ingress | 15 min |

**Communication:** Status page update within 10 minutes. Post-mortem within 48 hours.

---

### P1: High Error Rate (>5%)

**Symptoms:** `rag_http_requests_total{status=5xx}` spike, user reports of failed queries.

**Diagnosis:**
```bash
# Error breakdown by endpoint
curl -s localhost:9090/api/v1/query \
  --data-urlencode 'query=sum by (endpoint) (rate(rag_http_requests_total{status=~"5.."}[5m]))'

# Recent error logs
kubectl logs -l app=rag-backend -n rag-platform --tail=100 | grep '"level":"error"'

# Check LLM provider status
curl -s https://status.openai.com/api/v2/status.json | jq .status
```

**Resolution paths:**

| Root Cause | Fix |
|------------|-----|
| LLM provider outage | Enable fallback provider in LLM gateway config |
| Qdrant timeout | Check node health, scale cluster |
| PostgreSQL connection pool exhausted | Verify PgBouncer, increase pool size |
| Rate limit misconfiguration | Adjust limits in ConfigMap |
| Bad code deploy | Rollback deployment |

---

### P2: Chat Latency Degraded (p95 > 3s)

**Symptoms:** Users report slow responses, `rag_http_request_duration_seconds` p95 elevated.

**Diagnosis:**
```bash
# Latency breakdown by stage
curl -s localhost:9090/api/v1/query \
  --data-urlencode 'query=histogram_quantile(0.95, rate(rag_retrieval_duration_seconds_bucket[5m]))'

# Check which stage is slow
# Stages: query_expansion, vector_search, bm25_search, reranking, total
```

**Resolution by stage:**

| Slow Stage | Action |
|------------|--------|
| query_expansion | Enable expansion cache; disable for low-confidence skip |
| vector_search | Scale Qdrant nodes; check collection sizes |
| bm25_search | Scale OpenSearch; check shard distribution |
| reranking | Scale reranker pods; enable cascade reranking |
| LLM generation | Check provider latency; enable streaming; reduce context size |

**Quick mitigation:** Scale API pods (+3) and reranker pods (+2). This handles 60% of latency issues.

---

### P2: Celery Queue Backlog

**Symptoms:** Documents stuck in `pending` status, `celery_queue_length` > 200.

**Diagnosis:**
```bash
# Queue depths
celery -A app.workers.celery_app inspect active_queues

# Worker status
celery -A app.workers.celery_app inspect stats

# Failed tasks
celery -A app.workers.celery_app inspect revoked
```

**Resolution:**

| Root Cause | Fix |
|------------|-----|
| Insufficient workers | `kubectl scale deployment rag-worker --replicas=+4` |
| Embedding API rate limit | Enable backoff, switch to local BGE model |
| Large file processing | Check for files > 50MB, move to bulk queue |
| Worker OOM on PDF | Increase worker memory, add PDF page limit |
| Poison document | Identify failing doc, mark as failed, skip |

**Backpressure:** If queue > 1000, enable upload throttling (return 503 with Retry-After).

---

### P1: Suspected Data Isolation Breach

**Symptoms:** User reports seeing another organization's data.

**Immediate actions:**
1. **Do NOT restart services** — preserve logs
2. Disable affected endpoint if scope is identifiable
3. Page Security team and Engineering Lead
4. Capture: request_id, user_id, workspace_id, timestamp
5. Query audit logs for the user's session

**Investigation:**
```sql
-- Check audit trail
SELECT * FROM audit_logs
WHERE user_id = '<reported_user>'
ORDER BY created_at DESC LIMIT 50;

-- Verify workspace membership
SELECT * FROM workspace_members
WHERE user_id = '<reported_user>';
```

**Post-incident:** Mandatory post-mortem, affected tenant notification within 72 hours (GDPR), fix deployment within 24 hours.

---

## Daily Operations

### Morning Check (15 minutes)

- [ ] Review overnight alert history — any unresolved?
- [ ] Check Grafana Platform Health dashboard — all green?
- [ ] Review error rate — < 0.5%?
- [ ] Check Celery queue depth — < 50?
- [ ] Review token spend — within daily budget?
- [ ] Check certificate expiry dates — > 30 days?

### Weekly Tasks

- [ ] Review SLO burn rate for the week
- [ ] Check PostgreSQL table sizes and partition health
- [ ] Review Qdrant collection count and disk usage
- [ ] Run evaluation pipeline on sample workspaces
- [ ] Review cost report — top 10 orgs by spend
- [ ] Check for failed documents > 24 hours old
- [ ] Verify backup completion for all data stores

### Monthly Tasks

- [ ] Rotate secrets (JWT key, API keys) — blue/green
- [ ] Review and adjust autoscaling policies
- [ ] Capacity planning review against growth projections
- [ ] Load test validation (quarterly, not monthly)
- [ ] Review super_admin access list
- [ ] Update runbook based on incidents this month

---

## Scaling Playbook

### Scale Up (Traffic Surge)

```bash
# 1. API pods (immediate)
kubectl scale deployment rag-backend --replicas=20 -n rag-platform

# 2. Reranker pods
kubectl scale deployment rag-reranker --replicas=8 -n rag-platform

# 3. Workers (if ingestion surge)
kubectl scale deployment rag-worker --replicas=24 -n rag-platform

# 4. Verify
kubectl get hpa -n rag-platform
watch kubectl top pods -n rag-platform
```

### Scale Down (After Surge)

Wait 30 minutes after metrics normalize, then:
```bash
# HPA will handle API pods automatically
# Manually scale workers back
kubectl scale deployment rag-worker --replicas=16 -n rag-platform
```

**Never scale down during business hours without monitoring for 30 minutes post-change.**

---

## Deployment Procedure

### Standard Deployment

```bash
# 1. Pre-deploy checks
kubectl get pods -n rag-platform  # all healthy?
# Run smoke tests against staging

# 2. Deploy (rolling update)
kubectl set image deployment/rag-backend \
  backend=ghcr.io/org/backend:$SHA -n rag-platform

# 3. Monitor rollout
kubectl rollout status deployment/rag-backend -n rag-platform --timeout=300s

# 4. Post-deploy validation
curl https://api.rag.example.com/health
# Run synthetic query test
# Check error rate for 10 minutes

# 5. Rollback if needed
kubectl rollout undo deployment/rag-backend -n rag-platform
```

### Database Migration

```bash
# 1. Backup
pg_dump rag_platform > backup_$(date +%Y%m%d).sql

# 2. Run migration (Alembic)
kubectl exec -it deploy/rag-backend -n rag-platform -- alembic upgrade head

# 3. Verify
kubectl exec -it deploy/rag-backend -n rag-platform -- alembic current
```

**Rule:** Schema migrations must be backward-compatible. No column drops in the same release as code changes.

---

## Maintenance Windows

| Maintenance | Window | Frequency | User Impact |
|-------------|--------|-----------|-------------|
| PostgreSQL minor upgrade | Sunday 02:00–04:00 UTC | Quarterly | 5 min failover |
| OpenSearch rolling restart | Sunday 03:00–05:00 UTC | Monthly | None (replicas) |
| Qdrant node replacement | Sunday 04:00–06:00 UTC | As needed | Slight latency |
| Certificate renewal | Automated (cert-manager) | Auto | None |
| Secret rotation | Sunday 02:00 UTC | Monthly | Re-login required |

Announce maintenance 72 hours in advance for any expected user impact.

---

## Contact & Escalation

| Severity | Response Time | Channel |
|----------|--------------|---------|
| P1 | 15 minutes | PagerDuty + Slack #incidents |
| P2 | 1 hour | Slack #incidents |
| P3 | Next business day | Jira ticket |

Post-mortem template: timeline, root cause, impact, action items, prevention.
