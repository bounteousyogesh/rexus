# REX-US — LLM Cost Comparison: Claude Opus vs Sonnet on Bedrock

Production deployment on AWS Bedrock (US East Ohio region). Embedding: Cohere Embed v4.

Source: [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/) — US East (Ohio)

---

## Model Pricing

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| **Claude Opus 4.6** | $5.00 | $25.00 |
| **Claude Sonnet 4.6** | $3.00 | $15.00 |
| Cohere Embed v4 (embedding) | $0.10 | — |

---

## What Happens Per User Action

**Search (incident lookup — no playbook):** Embedding call only. Cost: effectively $0.

**Analysis with playbook:** Embedding + 2 LLM calls (playbook + resolution notes).

| Component | Input Tokens | Output Tokens |
|-----------|-------------|---------------|
| Embedding (Cohere v4) | ~200 | 0 |
| Playbook generation | ~5,500 | ~1,400 |
| Resolution notes | ~8,500 | ~2,700 |
| **Total per playbook** | **~14,000** | **~4,100** |

*Token estimates include 50% buffer over observed averages for safety margin.*

### Cost Per Playbook Generation

| | Claude Opus 4.6 | Claude Sonnet 4.6 |
|--|-----------------|-------------------|
| **Cost per playbook** | **$0.17** | **$0.10** |

---

## Monthly Cost — 12 Analysts

Each analyst: ~15 searches/day + ~10 playbook generations/day.

**Per analyst per day:**

| | Opus | Sonnet |
|--|------|--------|
| 15 searches (embedding only) | ~$0.00 | ~$0.00 |
| 10 playbooks | $1.72 | $1.01 |
| **Daily per analyst** | **$1.72** | **$1.01** |

**Team of 12, 22 working days/month:**

| | Opus | Sonnet |
|--|------|--------|
| Daily (12 analysts) | $20.64 | $12.12 |
| **Monthly** | **$454** | **$267** |
| **Annual** | **$5,449** | **$3,197** |
| **Difference** | | **Opus is +$187/month** |

---

## Summary

| | Sonnet 4.6 | Opus 4.6 |
|--|------------|----------|
| Per playbook | $0.10 | $0.17 |
| Per analyst/day (10 playbooks) | $1.01 | $1.72 |
| Monthly (12 analysts) | **$267** | **$454** |
| Annual | **$3,197** | **$5,449** |

---

## Recommendation

The difference between Opus and Sonnet is **$187/month** ($2,252/year) for 12 analysts at 10 playbooks each per day. For the best playbook quality, **use Opus**. If cost is a concern, Sonnet delivers good quality at 40% less.

Switching models requires no code change — single environment variable:

```
LLM_CHAT_MODEL=anthropic.claude-opus-4-6-v1       # recommended
LLM_CHAT_MODEL=anthropic.claude-sonnet-4-6         # alternative
```

**Note:** These are standard on-demand rates (highest tier). Actual costs will likely be lower due to Bedrock's automatic prompt caching — our system prompt is identical across calls, so cached input tokens are charged at $0.50/1M (Opus) instead of $5.00/1M. This could reduce costs by 20-30%.

---

## One-Time Setup Cost

| Activity | Cost |
|----------|------|
| Embed 20,000 incidents (Cohere v4) | ~$0.25 |

---

*Pricing source: [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/) — US East (Ohio) | 2026-04-09*
