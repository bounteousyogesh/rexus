# REX-US — Token Usage & Cost Report

Source: [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing)

---

## Cost Summary Per Tenant

Recommended model: **GPT-5.4** ($2.50/1M input, $15.00/1M output)

| Activity | Frequency | Cost |
|----------|-----------|------|
| **One-time setup** (embed 25,000 incidents) | Once per environment | **$0.06** |
| **Monthly sync** (500 new incidents) | Monthly | **$0.001** |
| **Incident analysis** (search + playbook) | Per analysis | **$0.064** |

### Monthly Operating Cost (per tenant)

| Analyses/Day | Monthly Cost (22 working days) | Annual |
|-------------|-------------------------------|--------|
| 10 | **$14** | $170 |
| 25 | **$35** | $424 |
| 50 | **$71** | $849 |

### Multi-Tenant Total (25 analyses/day per tenant)

| Tenants | One-Time Setup (each) | Monthly Operating |
|---------|----------------------|-------------------|
| 1 | $0.06 | $35 |
| 5 | $0.30 | $175 |
| 10 | $0.60 | $350 |
| 20 | $1.20 | $700 |

Setup must be run per environment (dev, staging, prod) or per server — each needs its own embedded knowledge base.

---

## What Happens Per Analysis

When a user uploads an incident, three things happen:

1. **Embedding** — incident text is converted to a 1536-dimension vector (text-embedding-3-small, ~127 tokens)
2. **Vector search** — database finds the 15 most similar incidents (zero LLM tokens — pure PostgreSQL)
3. **Playbook generation** — two parallel GPT-5.4 calls produce a concise playbook (~3,700 input / ~900 output tokens) and detailed resolution notes (~5,700 input / ~1,800 output tokens)

| Step | Tokens | Cost |
|------|--------|------|
| Embedding | 127 | $0.000003 |
| Vector search + DB queries | 0 | $0.00 |
| Playbook (input + output) | 4,600 | $0.023 |
| Resolution notes (input + output) | 7,500 | $0.041 |
| **Total** | **~12,200** | **$0.064** |

Playbook generation is 99% of the cost. Embeddings and search are effectively free.

---

## Model Options

| Model | Per Analysis | Monthly (25/day) | Quality |
|-------|-------------|------------------|---------|
| **GPT-5.4** | $0.064 | $35 | Best — recommended |
| GPT-5.4 Mini | $0.019 | $11 | Good |
| GPT-5.4 Nano | $0.005 | $3 | Basic |

### Full Pricing (per 1M tokens)

| Model | Input | Cached Input | Output | Batch Input | Batch Output |
|-------|-------|-------------|--------|-------------|-------------|
| GPT-5.4 | $2.50 | $0.25 | $15.00 | $1.25 | $7.50 |
| GPT-5.4 Mini | $0.75 | $0.075 | $4.50 | $0.375 | $2.25 |
| GPT-5.4 Nano | $0.20 | $0.02 | $1.25 | $0.10 | $0.625 |
| text-embedding-3-small | $0.02 | — | — | — | — |

---

## Validation Costs (Already Incurred — One-Time)

| Activity | Tokens | Cost |
|----------|--------|------|
| Wave testing (1,899 analyses) | ~23M | ~$96 |
| GPT-5.4 semantic validation (692 incidents) | 918K | ~$16 |
| **Total** | **~24M** | **~$112** |

---

*Source: [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing) | 2026-04-02 | REX-US v7*
