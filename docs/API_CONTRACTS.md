# API Contracts

Base URL: `/api/v1`

Authentication: `Authorization: Bearer <access_token>`

## Authentication

### POST /auth/register
```json
// Request
{
  "email": "user@company.com",
  "password": "securepass123",
  "full_name": "John Doe",
  "organization_name": "Acme Corp"  // optional, creates org
}

// Response 201
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### POST /auth/login
```json
// Request
{ "email": "user@company.com", "password": "securepass123" }

// Response 200 — same as register
```

### POST /auth/refresh
```json
// Request
{ "refresh_token": "eyJ..." }

// Response 200 — new token pair
```

### GET /auth/me
```json
// Response 200
{
  "id": "uuid",
  "email": "user@company.com",
  "full_name": "John Doe",
  "role": "org_admin",
  "is_active": true,
  "organization_id": "uuid"
}
```

## Workspaces

### POST /workspaces
```json
// Request
{ "name": "Engineering Docs", "description": "...", "chunking_strategy": "recursive" }

// Response 201
{
  "id": "uuid",
  "name": "Engineering Docs",
  "organization_id": "uuid",
  "member_count": 1,
  "document_count": 0,
  "chunking_strategy": "recursive",
  "created_at": "2026-01-01T00:00:00Z"
}
```

### GET /workspaces?page=1&page_size=20
```json
// Response 200
{
  "items": [/* WorkspaceResponse[] */],
  "total": 5,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### POST /workspaces/{id}/members
```json
// Request
{ "email": "colleague@company.com", "role": "member" }
```

## Documents

### POST /documents/upload?workspace_id={uuid}
```
Content-Type: multipart/form-data
file: <binary>

// Response 201
{
  "id": "uuid",
  "file_name": "policy.pdf",
  "status": "pending",
  "message": "Document uploaded and queued for processing"
}
```

### GET /documents?workspace_id={uuid}&status=completed&page=1
```json
// Response 200 — PaginatedResponse<DocumentResponse>
{
  "items": [{
    "id": "uuid",
    "file_name": "policy.pdf",
    "file_type": "pdf",
    "file_size": 1048576,
    "status": "completed",
    "chunk_count": 42,
    "page_count": 15,
    "created_at": "2026-01-01T00:00:00Z"
  }],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

## Chat

### POST /chat
```json
// Request
{
  "message": "What is the remote work policy?",
  "workspace_id": "uuid",
  "conversation_id": "uuid",  // optional
  "stream": false
}

// Response 200
{
  "conversation_id": "uuid",
  "message_id": "uuid",
  "content": "Employees may work remotely up to 3 days per week...",
  "citations": [{
    "document_id": "uuid",
    "file_name": "hr-policy.pdf",
    "page_number": 12,
    "chunk_index": 5,
    "content_snippet": "Remote work policy allows...",
    "relevance_score": 0.92
  }],
  "model": "gpt-4o",
  "latency_ms": 2340,
  "token_count": 256
}
```

### POST /chat/stream
Server-Sent Events stream:
```
data: {"type": "metadata", "conversation_id": "...", "citations": [...]}
data: {"type": "content", "content": "Employees"}
data: {"type": "content", "content": " may work"}
data: {"type": "done", "message_id": "..."}
```

### GET /chat/conversations?workspace_id={uuid}
### GET /chat/conversations/{id}/messages

## Analytics

### GET /analytics/usage?days=30
```json
// Response 200
{
  "summary": {
    "total_queries": 1250,
    "total_tokens": 450000,
    "total_cost_usd": 12.50,
    "avg_latency_ms": 2100,
    "avg_retrieval_ms": 450
  },
  "daily_metrics": [{
    "date": "2026-01-01",
    "queries": 45,
    "tokens": 15000,
    "cost_usd": 0.45,
    "avg_latency_ms": 1980
  }],
  "top_workspaces": [],
  "provider_breakdown": {}
}
```

### POST /analytics/evaluation
```json
// Request
{ "workspace_id": "uuid", "framework": "ragas" }

// Response 201
{
  "id": "uuid",
  "status": "pending",
  "framework": "ragas"
}
```

## Error Responses

```json
// 400/401/403/404/422/429/503
{
  "error": "Human-readable message",
  "details": { /* optional context */ }
}
```

## Rate Limits

- Default: 60 requests per minute per IP
- Returns 429 when exceeded
- Exempt: `/health`, `/metrics`, `/docs`
