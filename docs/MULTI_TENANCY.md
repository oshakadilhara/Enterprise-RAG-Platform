# Multi-Tenancy & Tenant Isolation — 100K Users

Multi-tenancy is the highest-risk architectural concern at 100K users. A single misconfiguration causes cross-tenant data leakage — an existential threat for enterprise customers.

## Tenancy Model

```
Platform
  └── Organization (tenant boundary — billing, limits, admin)
        └── Workspace (data boundary — indexes, documents, chat)
              └── User (access boundary — RBAC, audit)
```

### Isolation Boundaries

| Boundary | What's Isolated | Enforcement Layer |
|----------|----------------|-------------------|
| Organization | Users, billing, settings, analytics | JWT `org_id` claim + DB queries |
| Workspace | Documents, chunks, vectors, chat | `workspace_id` on every query |
| User | Conversations, personal history | `user_id` on conversation queries |

**Rule:** Every data access path must include `workspace_id` or `organization_id` — no exceptions. Code review checklist item.

---

## Data Isolation Architecture

### Storage Layer Isolation

| Store | Isolation Method | Cross-Tenant Risk |
|-------|-----------------|-------------------|
| PostgreSQL | `organization_id` / `workspace_id` FK + query filters | Low (if queries are scoped) |
| Qdrant | Separate collection per workspace | Very low (physical separation) |
| OpenSearch | Separate index per workspace | Very low (physical separation) |
| S3 | Prefix per org: `s3://bucket/{org_id}/{workspace_id}/` | Low (IAM policy) |
| Redis cache | Key prefix: `{org_id}:{workspace_id}:*` | Medium (key collision) |

### Query Path Validation

Every retrieval query must pass this gate:

```python
async def retrieve(query, workspace_id, current_user):
    # 1. Verify user is member of workspace
    membership = await member_repo.get_membership(workspace_id, current_user.id)
    if not membership:
        raise ForbiddenError()

    # 2. Verify workspace belongs to user's organization
    workspace = await workspace_repo.get_by_id(workspace_id)
    if workspace.organization_id != current_user.organization_id:
        raise ForbiddenError()

    # 3. Only then execute search (scoped to workspace_id)
    results = await hybrid_search.search(query, workspace_id)
```

**Never accept `workspace_id` from the client without membership verification.**

---

## Noisy Neighbor Prevention

At 5,000 organizations sharing infrastructure, resource hogging is inevitable without enforcement.

### Resource Quotas by Tier

| Resource | Starter | Business | Enterprise |
|----------|---------|----------|------------|
| Users | 10 | 100 | Unlimited |
| Workspaces | 3 | 20 | Unlimited |
| Documents | 100 | 5,000 | Unlimited |
| Chunks | 10K | 500K | 5M |
| Queries/day | 100 | 5,000 | 50,000 |
| Tokens/day | 100K | 2M | 20M |
| Upload rate | 10/hr | 50/hr | 200/hr |
| Max file size | 10 MB | 50 MB | 100 MB |
| Concurrent queries | 2 | 10 | 50 |

### Enforcement Points

```
Request → API Gateway
            ├── Rate limit check (Redis: org + user counters)
            ├── Token budget check (Redis: org daily spend)
            ├── Quota check (PostgreSQL: org document count)
            └── Proceed or 429/402
```

### Fair Scheduling (Celery)

```python
# Prevent one org from monopolizing ingestion queue
CELERY_TASK_ROUTES = {
    "process_document": {
        "queue": f"ingestion.{org_id % 4}",  # 4 queues, hash by org
    }
}

# Per-org concurrency limit
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ANNOTATIONS = {
    "process_document": {"rate_limit": "20/m"},  # per worker, per org
}
```

---

## Tenant Lifecycle

### Onboarding

```
1. Register organization → create org record
2. Create default workspace → provision Qdrant collection + OpenSearch index
3. Assign org_admin role to creator
4. Initialize usage counters in Redis
5. Audit log: org.created
```

### Workspace Provisioning

Creating a workspace triggers infrastructure provisioning:

```
1. INSERT workspace (PostgreSQL)
2. CREATE Qdrant collection: rag_{workspace_id}
3. CREATE OpenSearch index: rag_{workspace_id}
4. INSERT workspace_member (creator as owner)
5. Audit log: workspace.created
```

**At 100K users with 25K workspaces:** Provisioning must be async. Do not block the API response on index creation. Return workspace immediately, provision indexes in background, mark `status: provisioning` until complete.

### Offboarding / Deletion

```
1. Soft-delete organization (is_active = false)
2. Revoke all user tokens
3. Queue background job:
   a. Delete all Qdrant collections for org workspaces
   b. Delete all OpenSearch indexes
   c. Delete S3 prefix
   d. Archive PostgreSQL data (retain 90 days for compliance)
   e. Purge Redis cache keys
4. Audit log: org.deleted
```

**GDPR right-to-erasure:** Complete deletion within 30 days. Audit logs anonymized (user_id → hash).

---

## Cross-Tenant Analytics

Platform operators need aggregate metrics without accessing tenant data.

| Allowed | Not Allowed |
|---------|-------------|
| Total queries per org (count) | Query content |
| Token usage per org (count) | Retrieved chunks |
| Error rate per org | Chat messages |
| Storage per org (bytes) | Document content |
| Active users per org (count) | User search behavior |

Implement via pre-aggregated `usage_metrics` table — never query tenant content tables for platform analytics.

---

## Security Testing for Tenancy

### Required Tests Before Production

| Test | Method | Pass Criteria |
|------|--------|---------------|
| Cross-workspace retrieval | User A queries workspace B | 403 Forbidden |
| Cross-org access | User in Org A accesses Org B workspace | 403 Forbidden |
| IDOR on documents | Guess document UUID from another workspace | 404 Not Found |
| IDOR on conversations | Access conversation by UUID | 404 (not 403, no leak) |
| Cache isolation | Org A query cached, Org B same query | Different results |
| Index isolation | Direct Qdrant query without workspace filter | Only own collection accessible |
| Token org claim tampering | Modify JWT org_id | 401 Unauthorized |

Run these as automated integration tests in CI on every deployment.

---

## Super Admin Access

`super_admin` role can access cross-organization data for platform operations. This is the highest-risk role.

**Controls:**
- Maximum 3 super_admin accounts
- MFA required (when SSO implemented)
- All super_admin actions logged to immutable audit store
- No super_admin access to chat message content (metadata only)
- Quarterly access review
- Super_admin cannot export bulk document content without approval workflow

---

## Compliance Mapping

| Requirement | Implementation |
|-------------|---------------|
| Data residency | Region-specific deployments (EU, US) |
| Tenant isolation | Workspace-scoped indexes + RBAC |
| Audit trail | `audit_logs` table, 12-month retention |
| Data deletion | Offboarding pipeline (30-day SLA) |
| Access control | RBAC with least privilege |
| Encryption at rest | KMS for S3, RDS, EBS |
| Encryption in transit | TLS 1.3 everywhere |

See [SECURITY_COMPLIANCE.md](SECURITY_COMPLIANCE.md) for full security documentation.
