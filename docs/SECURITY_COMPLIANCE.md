# Security & Compliance

Enterprise security architecture for 100K users handling confidential company documents. Security is not a feature — it is a prerequisite for every scaling decision.

## Threat Model

| Threat | Likelihood | Impact | Mitigation |
|--------|-----------|--------|------------|
| Cross-tenant data leak | Medium | Critical | Workspace isolation + membership checks |
| JWT theft / session hijack | Medium | High | Short-lived tokens, refresh rotation |
| Prompt injection via documents | High | Medium | Input sanitization, system prompt hardening |
| LLM data exfiltration | Low | Critical | Provider DPA, no training opt-out |
| DDoS / resource exhaustion | High | High | WAF, rate limits, org quotas |
| Insider threat (admin abuse) | Low | Critical | Audit logs, least privilege |
| Upload malware | Medium | Medium | Type validation, sandboxed extraction |
| API key exposure | Medium | High | Secrets Manager, key rotation |

---

## Authentication Architecture

### JWT Token Lifecycle

```
Login → Access Token (30 min) + Refresh Token (7 days)
         │                        │
         │ API requests           │ Token refresh
         │ (Bearer header)        │ (single-use rotation)
         ▼                        ▼
    Validate JWT            Validate refresh
    Check role/perms        Issue new pair
    Check is_active         Revoke old refresh
```

**Token claims:**
```json
{
  "sub": "user-uuid",
  "role": "org_admin",
  "org_id": "org-uuid",
  "type": "access",
  "exp": 1718035200
}
```

### Security Controls

| Control | Implementation | Scale Consideration |
|---------|---------------|---------------------|
| Password hashing | bcrypt (cost 12) | CPU cost acceptable at login frequency |
| Token storage (client) | HttpOnly cookie (preferred) or secure localStorage | XSS risk with localStorage |
| Refresh token rotation | Single-use, stored as SHA-256 hash | DB lookup per refresh — index on hash |
| Token revocation | Redis blocklist for compromised tokens | TTL = remaining token lifetime |
| Brute force protection | 5 failed logins → 15 min lockout per email | Redis counter |
| MFA | Planned (Phase 7) | TOTP via authenticator app |

---

## Authorization (RBAC)

### Role Hierarchy

```
super_admin (100) > org_admin (80) > manager (50) > employee (10)
```

Higher roles inherit all permissions of lower roles within their scope.

### Permission Matrix

| Permission | super_admin | org_admin | manager | employee |
|------------|:-----------:|:---------:|:-------:|:--------:|
| org:create | ✓ | — | — | — |
| org:update | ✓ | ✓ | — | — |
| user:create | ✓ | ✓ | — | — |
| user:delete | ✓ | ✓ | — | — |
| workspace:create | ✓ | ✓ | ✓ | — |
| workspace:delete | ✓ | ✓ | — | — |
| document:upload | ✓ | ✓ | ✓ | — |
| document:delete | ✓ | ✓ | ✓ | — |
| document:read | ✓ | ✓ | ✓ | ✓ |
| chat:create | ✓ | ✓ | ✓ | ✓ |
| analytics:read | ✓ | ✓ | ✓ | — |
| evaluation:run | ✓ | ✓ | — | — |
| settings:manage | ✓ | ✓ | — | — |

### Enforcement Pattern

```python
# Every protected endpoint
@router.post("/documents/upload")
async def upload(current_user: CurrentUserDep):
    current_user.require_permission("document:create")
    # ... membership check for workspace
    # ... proceed
```

**At 100K users:** Permission checks are in-memory (role → permissions dict). No DB lookup per request. Membership check requires one indexed DB query.

---

## Data Protection

### Encryption

| Layer | Method | Key Management |
|-------|--------|---------------|
| In transit | TLS 1.3 (all endpoints) | ACM certificates |
| At rest — RDS | AES-256 (AWS managed) | KMS |
| At rest — S3 | SSE-KMS | Per-org KMS key (enterprise) |
| At rest — EBS | AES-256 | AWS managed |
| At rest — Redis | Encryption in transit + at rest | ElastiCache |
| Application secrets | AWS Secrets Manager | Auto-rotation (monthly) |

### Data Classification

| Class | Examples | Handling |
|-------|----------|----------|
| Public | Marketing docs, API docs | No restrictions |
| Internal | Workspace names, user emails | Org-scoped access |
| Confidential | Uploaded documents, chat content | Workspace-scoped, encrypted |
| Restricted | API keys, passwords, tokens | Secrets Manager, never logged |

### PII Handling

| Data | Stored | Retention | Deletion |
|------|--------|-----------|----------|
| Email | PostgreSQL | Account lifetime | On account deletion |
| Full name | PostgreSQL | Account lifetime | On account deletion |
| IP address | audit_logs | 12 months | Auto-purge |
| Query content | NOT logged | — | — |
| Chat messages | PostgreSQL | 12 months → archive | On request (GDPR) |
| Uploaded documents | S3 | Workspace lifetime | On workspace deletion |

---

## Prompt Injection Defense

Uploaded documents are untrusted input that becomes LLM context. At scale, this is a significant attack surface.

### Defenses

1. **System prompt hardening** — Instruct LLM to only use provided context, ignore instructions in documents
2. **Content delimitation** — Wrap chunk content in clear delimiters: `<context>...</context>`
3. **Input length limits** — Max 10,000 chars per user query
4. **Output validation** — Reject responses containing system prompt fragments
5. **Document scanning** — Flag documents with suspicious patterns (e.g., "ignore previous instructions")

### Monitoring

Log and alert on:
- Queries containing known injection patterns
- LLM responses that reference system instructions
- Unusual token usage spikes per user (possible exfiltration attempt)

---

## Network Security

```
Internet
  │
  ▼
┌─────────┐
│   WAF   │ ← SQL injection, XSS, rate limiting, geo-blocking
└────┬────┘
     │
┌────▼────┐
│   ALB   │ ← TLS termination, path routing
└────┬────┘
     │
┌────▼────────────────────────────┐
│  Private Subnet (EKS pods)      │
│  ┌─────────┐  ┌─────────────┐  │
│  │ Backend │  │  Workers    │  │
│  └────┬────┘  └──────┬──────┘  │
└───────┼──────────────┼──────────┘
        │              │
┌───────▼──────────────▼──────────┐
│  Isolated Subnet (Data tier)    │
│  RDS │ Redis │ Qdrant │ OS      │
│  (no internet access)           │
└─────────────────────────────────┘
```

### Security Groups

| Source | Destination | Port | Purpose |
|--------|-------------|------|---------|
| ALB | API pods | 8000 | HTTP |
| API pods | PgBouncer | 6432 | PostgreSQL |
| API pods | Redis | 6379 | Cache |
| API pods | Qdrant | 6333 | Vector search |
| API pods | OpenSearch | 9200 | Full-text search |
| Workers | All data tier | Same | Ingestion |
| Everything else | DENY | — | — |

---

## Audit & Compliance

### Audit Log Requirements

Every mutation (POST, PUT, PATCH, DELETE) logs:

```json
{
  "user_id": "uuid",
  "organization_id": "uuid",
  "action": "document.upload",
  "resource_type": "document",
  "resource_id": "uuid",
  "ip_address": "10.0.1.5",
  "timestamp": "2026-06-10T14:30:00Z",
  "details": {"file_name": "policy.pdf", "file_size": 1048576}
}
```

### Retention

| Log Type | Retention | Storage |
|----------|-----------|---------|
| Audit logs | 12 months | PostgreSQL → S3 archive |
| Access logs (ALB) | 90 days | S3 |
| Application logs | 30 days | CloudWatch |
| Security events | 24 months | Immutable S3 (Object Lock) |

### Compliance Roadmap

| Standard | Status | Key Requirements |
|----------|--------|-----------------|
| SOC 2 Type II | Planned (Phase 7) | Access controls, audit, encryption |
| GDPR | Architecture ready | Right to erasure, data portability |
| HIPAA | Not targeted | Would require BAA with LLM providers |
| ISO 27001 | Planned | ISMS, risk assessment |

---

## LLM Provider Security

### Data Processing Agreements

| Provider | Training on API data | Data residency | Enterprise DPA |
|----------|---------------------|----------------|----------------|
| OpenAI | Opt-out available | US (default) | Available |
| Anthropic | No training | US | Available |
| Google Gemini | Opt-out available | Configurable | Available |
| AWS Bedrock | No training | Regional | AWS BAA |

**Policy:** All LLM API calls must use enterprise endpoints with training opt-out. Document this in customer contracts.

### Provider Failover Security

When falling back to alternate provider:
- Same data processing agreement must cover the fallback
- Do not send to providers without DPA, even during outage
- Log which provider handled each query for audit

---

## Security Testing Schedule

| Test | Frequency | Scope |
|------|-----------|-------|
| OWASP ZAP scan | Weekly (CI) | API endpoints |
| Dependency audit | Daily (CI) | pip audit, npm audit |
| RBAC integration tests | Every deploy | All permission combinations |
| Tenant isolation tests | Every deploy | Cross-org/workspace access |
| Penetration test | Annual | Full platform |
| Secret rotation drill | Monthly | JWT keys, API keys |

---

## Incident Response (Security)

See [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) for the data isolation breach procedure.

**Security incident classification:**
- **SEV-1:** Confirmed data breach → notify affected tenants within 72 hours
- **SEV-2:** Suspected breach, no confirmation → investigate within 4 hours
- **SEV-3:** Vulnerability discovered, not exploited → patch within 7 days
