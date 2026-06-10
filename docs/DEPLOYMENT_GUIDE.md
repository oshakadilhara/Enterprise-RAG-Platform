# Production Deployment Guide

## Prerequisites

- Kubernetes 1.28+ cluster (EKS, GKE, or self-managed)
- kubectl configured
- Docker images built and pushed to registry
- Domain with DNS access
- SSL certificate (cert-manager recommended)

## Step 1: Infrastructure Provisioning

### Database (PostgreSQL 16)
```bash
# RDS or managed PostgreSQL
createdb rag_platform
psql rag_platform < infrastructure/init-db.sql
```

### Redis 7
```bash
# ElastiCache or managed Redis
# Connection: redis://host:6379/0
```

### Qdrant
```bash
kubectl apply -f https://raw.githubusercontent.com/qdrant/qdrant/master/kubernetes/qdrant-cluster.yaml
```

### OpenSearch
```bash
# AWS OpenSearch Service or self-hosted
# Ensure security plugin configured
```

## Step 2: Configure Secrets

```bash
# Edit secrets before applying
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/secrets.yaml
kubectl apply -f infrastructure/kubernetes/configmap.yaml
```

**Required secrets:**
- `SECRET_KEY` — 32+ char random string
- `JWT_SECRET_KEY` — Separate random string
- `DATABASE_URL` — PostgreSQL connection string
- `OPENAI_API_KEY` — Or other LLM provider key
- `OPENSEARCH_PASSWORD`

## Step 3: Deploy Application

```bash
# Apply all manifests
kubectl apply -f infrastructure/kubernetes/

# Verify deployments
kubectl get pods -n rag-platform
kubectl logs -f deployment/rag-backend -n rag-platform
```

## Step 4: Configure Ingress

```bash
# Install NGINX Ingress Controller (if not present)
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx

# Install cert-manager for TLS
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Apply ingress
kubectl apply -f infrastructure/kubernetes/ingress.yaml
```

## Step 5: Verify Deployment

```bash
# Health check
curl https://api.rag.example.com/health

# API docs (if debug enabled)
curl https://api.rag.example.com/docs

# Frontend
open https://rag.example.com
```

## Step 6: Monitoring Setup

### Prometheus
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring
```

### Grafana Dashboards
Import dashboards for:
- HTTP request latency (p50, p95, p99)
- RAG query count and success rate
- Token usage by provider
- Document processing throughput
- Celery worker queue depth

### Alerts
Configure alerts for:
- API error rate > 5%
- P95 latency > 5s
- Worker queue depth > 100
- Database connection pool exhaustion

## Step 7: Backup Strategy

| Data | Method | Frequency |
|------|--------|-----------|
| PostgreSQL | RDS automated snapshots | Daily |
| Qdrant | Volume snapshots | Daily |
| OpenSearch | Automated snapshots | Daily |
| S3 Documents | Cross-region replication | Continuous |
| Redis | AOF persistence | Continuous |

## Scaling Guidelines

### Horizontal Scaling
```bash
# Scale API servers
kubectl scale deployment rag-backend --replicas=5 -n rag-platform

# Scale workers
kubectl scale deployment rag-worker --replicas=4 -n rag-platform
```

### When to Scale
| Metric | Threshold | Action |
|--------|-----------|--------|
| API CPU | > 70% sustained | Add backend replicas |
| Worker queue | > 50 pending | Add worker replicas |
| P95 latency | > 3s | Scale API + check DB |
| DB connections | > 80% pool | Add read replica |

## Rollback Procedure

```bash
# Rollback to previous deployment
kubectl rollout undo deployment/rag-backend -n rag-platform
kubectl rollout undo deployment/rag-frontend -n rag-platform

# Verify
kubectl rollout status deployment/rag-backend -n rag-platform
```

## Environment-Specific Configuration

| Setting | Staging | Production |
|---------|---------|------------|
| DEBUG | true | false |
| Replicas (API) | 1 | 3+ |
| Replicas (Worker) | 1 | 2+ |
| Rate Limit | 120/min | 60/min |
| DB Instance | db.t3.medium | db.r6g.xlarge |
| Log Level | DEBUG | INFO |
