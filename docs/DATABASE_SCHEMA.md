# Database Schema

## Entity Relationship Diagram

```
organizations ──┬── users
                └── workspaces ──┬── workspace_members
                                 ├── documents ── document_chunks
                                 └── conversations ── messages

usage_metrics (organization-level tracking)
audit_logs (security compliance)
evaluation_runs (RAG quality metrics)
refresh_tokens (auth)
```

## Tables

### organizations
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Organization identifier |
| name | VARCHAR(255) | Display name |
| slug | VARCHAR(100) UNIQUE | URL-friendly identifier |
| description | TEXT | Optional description |
| is_active | BOOLEAN | Active status |
| settings | TEXT | JSON configuration |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update |

### users
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | User identifier |
| email | VARCHAR(255) UNIQUE | Login email |
| hashed_password | VARCHAR(255) | bcrypt hash |
| full_name | VARCHAR(255) | Display name |
| role | VARCHAR(50) | super_admin, org_admin, manager, employee |
| is_active | BOOLEAN | Account status |
| organization_id | UUID FK | Parent organization |
| last_login_at | TIMESTAMPTZ | Last login |
| created_at | TIMESTAMPTZ | Creation timestamp |

### workspaces
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Workspace identifier |
| name | VARCHAR(255) | Display name |
| organization_id | UUID FK | Parent organization |
| created_by | UUID FK | Creator user |
| chunking_strategy | VARCHAR(50) | fixed, recursive, semantic |
| embedding_model | VARCHAR(100) | Override embedding model |

### workspace_members
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Membership identifier |
| workspace_id | UUID FK | Workspace |
| user_id | UUID FK | User |
| role | VARCHAR(50) | owner, admin, member, viewer |
| joined_at | TIMESTAMPTZ | Join date |

**Unique constraint:** (workspace_id, user_id)

### documents
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Document identifier |
| workspace_id | UUID FK | Parent workspace |
| owner_id | UUID FK | Uploading user |
| file_name | VARCHAR(500) | Original filename |
| file_type | VARCHAR(20) | pdf, docx, txt, csv |
| file_size | BIGINT | Size in bytes |
| storage_path | VARCHAR(1000) | S3/local path |
| status | VARCHAR(50) | pending, processing, completed, failed |
| chunk_count | INTEGER | Number of chunks |
| page_count | INTEGER | Number of pages |
| error_message | TEXT | Processing error |

### document_chunks
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Chunk identifier |
| document_id | UUID FK | Parent document |
| workspace_id | UUID FK | Workspace (denormalized) |
| chunk_index | INTEGER | Order in document |
| content | TEXT | Chunk text |
| page_number | INTEGER | Source page |
| token_count | INTEGER | Token count |
| vector_id | VARCHAR(100) | Qdrant point ID |
| opensearch_id | VARCHAR(100) | OpenSearch doc ID |

### conversations
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Conversation identifier |
| user_id | UUID FK | Owner |
| workspace_id | UUID FK | Knowledge scope |
| title | VARCHAR(500) | Conversation title |
| is_archived | BOOLEAN | Archive status |

### messages
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Message identifier |
| conversation_id | UUID FK | Parent conversation |
| role | VARCHAR(20) | user, assistant, system |
| content | TEXT | Message text |
| citations_json | TEXT | JSON array of citations |
| token_count | INTEGER | Tokens used |
| latency_ms | INTEGER | Response time |
| model | VARCHAR(100) | LLM model used |

### usage_metrics
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Metric identifier |
| organization_id | UUID FK | Organization |
| user_id | UUID FK | User (optional) |
| workspace_id | UUID | Workspace (optional) |
| metric_type | VARCHAR(50) | query, embedding, llm |
| tokens_input | INTEGER | Input tokens |
| tokens_output | INTEGER | Output tokens |
| latency_ms | INTEGER | Total latency |
| retrieval_ms | INTEGER | Retrieval latency |
| cost_usd | FLOAT | Estimated cost |
| provider | VARCHAR(50) | AI provider |
| model | VARCHAR(100) | Model name |

### audit_logs
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Log identifier |
| user_id | UUID FK | Acting user |
| action | VARCHAR(100) | Action performed |
| resource_type | VARCHAR(50) | Target resource type |
| resource_id | VARCHAR(100) | Target resource ID |
| ip_address | VARCHAR(45) | Client IP |
| details | TEXT | Additional context |

### evaluation_runs
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Run identifier |
| workspace_id | UUID FK | Evaluated workspace |
| framework | VARCHAR(50) | ragas, deepeval |
| status | VARCHAR(50) | pending, running, completed, failed |
| precision_at_k | FLOAT | Precision@K score |
| recall_at_k | FLOAT | Recall@K score |
| mrr | FLOAT | Mean Reciprocal Rank |
| ndcg | FLOAT | Normalized DCG |
| faithfulness | FLOAT | Answer faithfulness |
| answer_relevancy | FLOAT | Answer relevancy |
| context_precision | FLOAT | Context precision |

## Indexes

- `users.email` — Login lookup
- `users.organization_id` — Org member queries
- `workspaces.organization_id` — Org workspace listing
- `documents.workspace_id` — Workspace document listing
- `document_chunks.document_id` — Chunk lookup
- `document_chunks.workspace_id` — Workspace chunk queries
- `conversations.user_id` — User conversation listing
- `messages.conversation_id` — Message history
- `usage_metrics.organization_id, created_at` — Analytics queries
- `audit_logs.user_id, created_at` — Audit queries

## Vector Storage (Qdrant)

Collection per workspace: `rag_{workspace_id}`

Payload fields:
- document_id, workspace_id, file_name, content
- page_number, chunk_index, upload_date

## Full-Text Index (OpenSearch)

Index per workspace: `rag_{workspace_id}`

Mapped fields: chunk_id, document_id, content (analyzed), file_name, page_number
