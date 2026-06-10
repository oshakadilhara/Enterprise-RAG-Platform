# AWS Architecture

## Overview

Production deployment on AWS using EKS (Elastic Kubernetes Service) with managed services for data persistence and observability.

```
                    ┌─────────────────────────────────────────┐
                    │              Route 53 DNS               │
                    └──────────────┬──────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────────┐
                    │         CloudFront CDN                  │
                    │    (Static assets + API caching)        │
                    └──────────────┬──────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────────┐
                    │      Application Load Balancer          │
                    │         (AWS Load Balancer Controller)  │
                    └──────────────┬──────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        ┌──────────┐        ┌──────────┐        ┌──────────┐
        │ Frontend │        │ Backend  │        │  Worker  │
        │  (EKS)   │        │  (EKS)   │        │  (EKS)   │
        └──────────┘        └────┬─────┘        └────┬─────┘
                                 │                    │
              ┌──────────────────┼────────────────────┤
              ▼                  ▼                    ▼
        ┌──────────┐    ┌──────────────┐    ┌──────────────┐
        │   RDS    │    │  ElastiCache │    │      S3      │
        │PostgreSQL│    │    Redis     │    │  Documents   │
        └──────────┘    └──────────────┘    └──────────────┘
              │
              ▼
        ┌──────────────┐    ┌──────────────┐
        │  OpenSearch  │    │   Qdrant     │
        │   Service    │    │  (EKS/EKS+)  │
        └──────────────┘    └──────────────┘
```

## Service Mapping

| Component | AWS Service | Configuration |
|-----------|-------------|---------------|
| Compute | EKS (3 node groups) | API: m5.xlarge, Worker: m5.2xlarge, Frontend: t3.medium |
| Database | RDS PostgreSQL 16 | Multi-AZ, db.r6g.xlarge, 500GB gp3 |
| Cache/Queue | ElastiCache Redis 7 | Cluster mode, cache.r6g.large |
| Object Storage | S3 | Standard tier, lifecycle to IA after 90 days |
| Full-Text Search | OpenSearch Service | r6g.large.search, 3 data nodes |
| Vector DB | Qdrant on EKS | Dedicated node group, NVMe storage |
| CDN | CloudFront | Frontend assets + API edge caching |
| DNS | Route 53 | rag.company.com, api.rag.company.com |
| Secrets | AWS Secrets Manager | API keys, DB credentials, JWT secrets |
| Monitoring | CloudWatch + AMP | Metrics, logs, alarms |
| Tracing | AWS X-Ray / ADOT | OpenTelemetry collector |
| AI (optional) | Amazon Bedrock | Claude, Titan embeddings |

## Network Architecture

```
VPC (10.0.0.0/16)
├── Public Subnets (10.0.1.0/24, 10.0.2.0/24)
│   ├── NAT Gateways
│   ├── ALB
│   └── Bastion (optional)
├── Private Subnets (10.0.10.0/24, 10.0.11.0/24)
│   ├── EKS Worker Nodes
│   ├── RDS PostgreSQL
│   ├── ElastiCache Redis
│   └── OpenSearch
└── Isolated Subnets (10.0.20.0/24, 10.0.21.0/24)
    └── Qdrant persistent volumes
```

## Security

- **WAF** on ALB — SQL injection, rate limiting, geo-blocking
- **Security Groups** — Least-privilege between tiers
- **IAM Roles** — IRSA for pod-level AWS access
- **Secrets Manager** — Rotated credentials
- **VPC Endpoints** — S3, Secrets Manager (no internet egress)
- **Encryption** — At rest (KMS) and in transit (TLS 1.3)

## Multi-Region Strategy

```
Primary (us-east-1)          DR (us-west-2)
├── EKS Cluster              ├── EKS Cluster (standby)
├── RDS Primary              ├── RDS Read Replica
├── S3 (primary)             ├── S3 Cross-Region Replication
├── OpenSearch               ├── OpenSearch (replica)
└── Route 53 (active)        └── Route 53 (failover)
```

## Cost Estimation (Monthly)

| Service | Spec | Est. Cost |
|---------|------|-----------|
| EKS Control Plane | 1 cluster | $73 |
| EKS Nodes | 6 × m5.xlarge | $1,100 |
| RDS PostgreSQL | db.r6g.xlarge Multi-AZ | $550 |
| ElastiCache | cache.r6g.large | $200 |
| OpenSearch | 3 × r6g.large.search | $600 |
| S3 | 1TB storage + requests | $30 |
| CloudFront | 500GB transfer | $50 |
| CloudWatch | Logs + metrics | $100 |
| **Total** | | **~$2,700/mo** |

*Excludes LLM API costs (variable based on usage)*

## Bedrock Integration

For AWS-native AI:
```python
# Environment override
LLM_PROVIDER=bedrock
LLM_MODEL=anthropic.claude-3-sonnet-20240229-v1:0
EMBEDDING_PROVIDER=bedrock
EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
```

## Deployment Steps

1. Provision VPC, subnets, security groups (Terraform)
2. Create EKS cluster with node groups
3. Deploy RDS, ElastiCache, OpenSearch via Terraform
4. Configure Secrets Manager with application secrets
5. Deploy K8s manifests with AWS-specific ConfigMaps
6. Configure ALB Ingress Controller
7. Set up CloudWatch dashboards and alarms
8. Enable S3 document storage with IRSA

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed steps.
