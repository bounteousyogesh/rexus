"""
REX-US — Token Usage Tracker

Logs every OpenAI API call (embeddings + completions) to the database
for monitoring, dashboards, and cost tracking.

Usage:
    from backend.api.utils.token_tracker import track_usage

    # After any OpenAI call:
    await track_usage(pool, "embedding", "text-embedding-3-small", 127, 0, endpoint="/analyze")
    await track_usage(pool, "completion", "gpt-5.4", 3700, 900, endpoint="/analyze")
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

# Model pricing per 1M tokens (source: https://developers.openai.com/api/docs/pricing)
MODEL_PRICING = {
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
    "gpt-5.4": {"input": 2.50, "output": 15.00},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # AWS Bedrock — Cohere Embed v3/v4 (price per 1M tokens)
    "cohere.embed-english-v3": {"input": 0.10, "output": 0.0},
    "cohere.embed-multilingual-v3": {"input": 0.10, "output": 0.0},
    "cohere.embed-v4:0": {"input": 0.10, "output": 0.0},
    # AWS Bedrock — Anthropic Claude (approximate, varies by version)
    "anthropic.claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "anthropic.claude-3-haiku": {"input": 0.25, "output": 1.25},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a single API call."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        # Bedrock inference profile ARNs contain the model family name — do substring match
        model_lower = model.lower()
        for key, p in MODEL_PRICING.items():
            if key in model_lower:
                pricing = p
                break
    if pricing is None:
        logger.warning(
            "Unknown model '%s' — using default pricing ($2.50/$15.00 per 1M tokens). "
            "Add this model to MODEL_PRICING in token_tracker.py for accurate cost tracking.",
            model,
        )
        pricing = {"input": 2.50, "output": 15.00}
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


async def track_usage(
    pool: "asyncpg.Pool",
    call_type: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    endpoint: str = "",
    incident_number: str = "",
):
    """
    Log a single OpenAI API call to rexus_token_usage.

    call_type: "embedding" | "completion"
    model: "text-embedding-3-small" | "gpt-5.4" | etc.
    """
    cost = estimate_cost(model, input_tokens, output_tokens)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO rexus_token_usage
                   (call_type, model, input_tokens, output_tokens, estimated_cost_usd, endpoint, incident_number)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                call_type, model, input_tokens, output_tokens, cost, endpoint, incident_number,
            )
    except Exception as e:
        # Never let tracking failures break the main flow
        logger.debug(f"Token tracking failed: {e}")
