# REX-US — AWS Deployment Plan

All services on Bedrock. No OpenAI. Fresh database. Full re-embed.

---

## What We're Building

```
Internet → ALB (port 80) → Frontend (nginx, port 80)   → serves React app
                          → Backend (uvicorn, port 8000) → serves API

Backend → RDS PostgreSQL 16 (pgvector, pg_trgm)   → knowledge base
Backend → Bedrock (Claude Opus 4.6)                → playbook generation
Backend → Bedrock (Cohere Embed v4, 1536 dims)     → embeddings
Backend → ServiceNow (DT Detailed API)             → incident fetch
```

---

## Services Used

| AWS Service | Purpose | Cost Estimate (dev) |
|-------------|---------|-------------------|
| VPC + Subnets | Networking | Free |
| NAT Gateway | Private subnet outbound | ~$32/month |
| ALB | Load balancer + routing | ~$16/month |
| ECR | Docker image registry | < $1/month |
| ECS Fargate | Run backend + frontend containers | ~$30/month (1 vCPU, 2GB each) |
| RDS PostgreSQL | Database with pgvector | ~$50/month (db.t4g.medium) |
| Secrets Manager | DB password, SN credentials | ~$2/month |
| Bedrock | Claude Opus + Cohere Embed v4 | ~$35/month (at 25 analyses/day) |

**Estimated total: ~$165/month for dev environment**

---

## Execution Steps

### Step 1: Foundation (Terraform)

**What:** VPC, 2 public + 2 private subnets, Internet Gateway, NAT Gateway, security groups (ALB, ECS, RDS)

**Script:** `infra/terraform/01-foundation/main.tf` (already written)

**Validate:** VPC visible in AWS Console. Security groups created.

---

### Step 2: Database (Terraform)

**What:** RDS PostgreSQL 16 in private subnets. DB credentials auto-generated and stored in Secrets Manager.

**Script:** `infra/terraform/02-database/main.tf`

**Creates:**
- RDS instance `rexus-dev` (db.t4g.medium, 50GB, PostgreSQL 16)
- DB subnet group across 2 private subnets
- Secrets Manager secret `rexus/dev/database` with auto-generated password
- Outputs the DATABASE_URL for later steps

**Validate:** Connect to RDS via bastion or temporarily open security group. Run `SELECT version();`

**Post-Terraform:** Run migrations against the new database:
```bash
psql $DATABASE_URL < backend/migrations/001_rexus_schema.sql
psql $DATABASE_URL < backend/migrations/002_enriched_schema.sql
psql $DATABASE_URL < backend/migrations/003_token_usage.sql
psql $DATABASE_URL < backend/migrations/004_indexes_and_extensions.sql
```

---

### Step 3: Container Registry (Terraform + Docker)

**What:** Two ECR repositories. Build and push Docker images.

**Script:** `infra/terraform/03-ecr/main.tf`

**Creates:**
- ECR repo `rexus-backend`
- ECR repo `rexus-frontend`

**Post-Terraform — Build and push images:**

Backend Dockerfile (corrected from DT's template):
```
infra/docker/Dockerfile.backend
```
- Python 3.13-slim
- Copies code to /app/backend/ (preserves import paths)
- Installs requirements + spaCy model
- CMD: uvicorn backend.api.main:app

Frontend Dockerfile (corrected):
```
infra/docker/Dockerfile.frontend
```
- Node 24 build stage → nginx runtime
- nginx proxies /api/* to backend, serves /* as SPA
- nginx.conf included

**Build + push script:**
```
infra/scripts/build-and-push.sh
```

**Validate:** Images visible in ECR Console. Pull and run locally to verify.

---

### Step 4: Load Balancer (Terraform)

**What:** ALB in public subnets with routing rules.

**Script:** `infra/terraform/04-alb/main.tf`

**Creates:**
- ALB `rexus-dev-alb` in public subnets
- Target group `rexus-backend` (port 8000, health check on /health)
- Target group `rexus-frontend` (port 80)
- HTTP listener (port 80):
  - `/api/*` → backend target group
  - `/health*` → backend target group
  - `/*` → frontend target group

**Validate:** ALB DNS name accessible (will return 503 until ECS services are running — that's expected).

---

### Step 5: Secrets + Config (Terraform)

**What:** Store ServiceNow credentials in Secrets Manager. Define ECS environment variables.

**Script:** `infra/terraform/05-secrets/main.tf`

**Creates:**
- Secret `rexus/dev/servicenow` with SN credentials (manually populated after creation)
- SSM Parameters for non-secret config:
  - `/rexus/dev/LLM_PROVIDER` = `bedrock`
  - `/rexus/dev/LLM_CHAT_MODEL` = `anthropic.claude-opus-4-6-v1`
  - `/rexus/dev/LLM_EMBED_MODEL` = `cohere.embed-v4:0`
  - `/rexus/dev/REXUS_ENV` = `development`
  - `/rexus/dev/REXUS_ORG_NAME` = `Discount Tire`

**Validate:** Secrets visible in Secrets Manager Console.

---

### Step 6: Compute — ECS Fargate (Terraform)

**What:** ECS cluster, task definitions, services, IAM roles.

**Script:** `infra/terraform/06-ecs/main.tf`

**Creates:**
- IAM role `rexus-task-execution-role`:
  - ECR pull (`AmazonECSTaskExecutionRolePolicy`)
  - Secrets Manager read (`secretsmanager:GetSecretValue` on `rexus/*`)
- IAM role `rexus-task-role`:
  - Bedrock invoke (`bedrock:InvokeModel` on `*`)
- ECS Cluster `rexus-dev`
- Task definition `rexus-backend`:
  - Image from ECR
  - Secrets injected from Secrets Manager (DATABASE_URL, SN creds)
  - Environment variables for config (LLM_PROVIDER, models, etc.)
  - Port 8000
  - Health check: `curl http://localhost:8000/health`
- Task definition `rexus-frontend`:
  - Image from ECR
  - Port 80
- ECS Service `rexus-backend` (desired count: 1, linked to ALB backend target group)
- ECS Service `rexus-frontend` (desired count: 1, linked to ALB frontend target group)

**Validate:** Hit ALB DNS → should see the React app. Hit ALB/health → should see healthy response.

---

### Step 7: Import Data + Re-Embed

**What:** Populate the fresh database with incidents, embedded using Cohere v4 via Bedrock.

**This runs AFTER the infrastructure is up.**

**Option A: Via the UI (recommended for last 6 months)**
1. Open REX-US in browser (ALB DNS)
2. Go to SN Sync tab
3. Search for closed incidents (incident_state=7)
4. Import groups day by day

**Option B: Via catalog script (for historical data)**
```bash
# From a machine that can reach the RDS database
python backend/scripts/import_from_catalog.py --from 2024-04-01 --to 2025-10-01
```
This uses the CSV catalog + DT Detailed API. Each incident is fetched, embedded with Cohere v4 (via Bedrock), and inserted.

**Option C: Bulk re-embed script (new — needs to be written)**
```
infra/scripts/bulk_embed_bedrock.py
```
- Reads incident_catalog.csv
- Fetches each incident via DT Detailed API
- Embeds using Bedrock Cohere v4 (`cohere.embed-v4:0`, 1536 dims)
- Inserts into RDS rexus_incidents_v3
- Checkpoint/resume support
- Estimated time: ~3-4 hours for 18K incidents

---

### Step 8: Validate End-to-End

**What:** Verify the full system works on AWS.

1. `GET /health` → healthy, database connected
2. `GET /health/detailed` → all checks pass (DB, Bedrock, SN connectivity)
3. `GET /api/v1/config/llm` → shows bedrock provider, Cohere embed, Claude Opus chat
4. Enter an INC number → fetch from SN → analyze → get playbook
5. Upload a PDF → analyze → get playbook
6. SN Sync → search → import a batch → verify they appear in the knowledge base
7. Check token usage → `/api/v1/token-usage?days=1`

---

## Scripts to Write

| Script | Purpose | When |
|--------|---------|------|
| `infra/docker/Dockerfile.backend` | Corrected backend Docker image | Step 3 |
| `infra/docker/Dockerfile.frontend` | Corrected frontend Docker image with nginx | Step 3 |
| `infra/docker/nginx.conf` | nginx config for frontend (SPA + API proxy) | Step 3 |
| `infra/scripts/build-and-push.sh` | Build Docker images and push to ECR | Step 3 |
| `infra/scripts/run-migrations.sh` | Run SQL migrations against RDS | Step 2 (post) |
| `infra/scripts/bulk_embed_bedrock.py` | Bulk import + embed using Bedrock Cohere v4 | Step 7 |

## Code Changes Needed

| Change | Why |
|--------|-----|
| Update `llm_provider.py` `_bedrock_embed()` | Add Cohere v4 request format (uses `texts` array + `input_type`, not `inputText`) |
| Update `llm_provider.py` response parsing | Cohere v4 returns `{"embeddings": {"float": [[...]]}}` not `{"embedding": [...]}` |
| Test Cohere v4 embedding quality | Run 100 incidents through search, compare results vs OpenAI embeddings |

---

## Order of Execution

```
Day 1:  Steps 1-3   — Foundation + Database + ECR (infra)
Day 1:  Build + push Docker images
Day 1:  Run migrations

Day 2:  Steps 4-6   — ALB + Secrets + ECS (infra)
Day 2:  Deploy containers
Day 2:  Validate health checks

Day 2:  Step 7      — Import + re-embed (runs in background, 3-4 hours)
Day 2:  Step 8      — End-to-end validation
```

---

## Rollback

Every Terraform step can be destroyed independently:
```bash
cd infra/terraform/06-ecs && terraform destroy   # remove containers first
cd infra/terraform/04-alb && terraform destroy   # then ALB
cd infra/terraform/02-database && terraform destroy  # then DB
cd infra/terraform/01-foundation && terraform destroy  # then VPC last
```

---

*Plan version: 1.0 | 2026-04-08*
