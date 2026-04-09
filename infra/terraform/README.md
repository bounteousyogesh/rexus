# REX-US — AWS Infrastructure (Terraform)

## Deployment Steps

Execute in order. Each step is a separate `terraform apply`. We validate after each step before moving to the next.

### Step 1: Foundation (VPC + Networking)
- VPC with 2 public + 2 private subnets across 2 AZs
- Internet Gateway for public subnets
- NAT Gateway for private subnet outbound (RDS, Bedrock API calls)
- Security groups for ALB, ECS tasks, and RDS

### Step 2: Database (RDS PostgreSQL + pgvector)
- RDS PostgreSQL 16 in private subnets
- pgvector extension enabled
- DB credentials stored in Secrets Manager
- Run schema migrations after creation

### Step 3: Container Registry (ECR)
- Two ECR repositories: rexus-backend, rexus-frontend
- Build and push Docker images
- Lifecycle policies to clean old images

### Step 4: Load Balancer (ALB)
- Application Load Balancer in public subnets
- Target groups for backend (port 8000) and frontend (port 80)
- Routing rules: /api/* and /health* → backend, /* → frontend
- HTTPS listener with ACM certificate (optional — HTTP for testing)

### Step 5: Secrets + Config
- Secrets Manager entries for ServiceNow credentials
- ECS-compatible secret references
- Environment variable definitions for ECS tasks

### Step 6: Compute (ECS Fargate)
- ECS Cluster
- Task definitions for backend and frontend
- Services with desired count, health checks, auto-scaling
- IAM roles: task execution role (ECR pull + Secrets Manager) and task role (Bedrock)

### Step 7: Validate
- Hit /health and /health/detailed
- Run a test analysis
- Verify DB connectivity, Bedrock connectivity, SN connectivity

---

## File Structure

```
infra/terraform/
  README.md              ← this file
  variables.tf           ← shared variables (region, project name, etc.)
  outputs.tf             ← shared outputs
  01-foundation/
    main.tf              ← VPC, subnets, IGW, NAT, security groups
    outputs.tf
  02-database/
    main.tf              ← RDS PostgreSQL, Secrets Manager (DB creds)
    outputs.tf
  03-ecr/
    main.tf              ← ECR repositories
    outputs.tf
  04-alb/
    main.tf              ← ALB, target groups, listeners, routing rules
    outputs.tf
  05-secrets/
    main.tf              ← Secrets Manager (SN creds), SSM params (config)
    outputs.tf
  06-ecs/
    main.tf              ← ECS cluster, task defs, services, IAM roles
    outputs.tf
```

## Prerequisites

- Terraform >= 1.5
- AWS CLI configured (`aws configure`)
- Docker (for building images in step 3)

## Quick Start

```bash
cd infra/terraform/01-foundation
terraform init
terraform plan
terraform apply
# Validate → then move to 02-database
```
</content>
