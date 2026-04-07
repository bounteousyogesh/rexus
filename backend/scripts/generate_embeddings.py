"""
REX-US — Embedding Generator

Takes ingested incidents JSON and generates OpenAI embeddings.
Saves enriched JSON with embeddings for database loading.

Usage:
    python generate_embeddings.py rexus/data/sn_incidents_full.json
    python generate_embeddings.py rexus/data/sn_incidents_full.json --batch-size 100
"""

import os
import sys
import json
import argparse
import logging
import time
from pathlib import Path
from typing import List

from dotenv import load_dotenv
# Load .env from repo root (REX-US/.env)
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# OpenAI embedding model
MODEL = "text-embedding-3-small"
DIMS = 1536
MAX_TOKENS = 8191
# OpenAI allows up to 2048 texts per batch
OPENAI_BATCH_LIMIT = 2048


def get_embeddings_batch(client: OpenAI, texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a batch of texts."""
    response = client.embeddings.create(
        model=MODEL,
        input=texts,
    )
    # Return in same order as input
    embeddings = [None] * len(texts)
    for item in response.data:
        embeddings[item.index] = item.embedding
    return embeddings


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for incidents")
    parser.add_argument("input_file", help="Path to ingested incidents JSON")
    parser.add_argument("--batch-size", type=int, default=200, help="Embedding batch size")
    parser.add_argument("--output", type=str, default=None, help="Output path")
    args = parser.parse_args()

    # Load incidents
    with open(args.input_file) as f:
        incidents = json.load(f)
    logger.info(f"Loaded {len(incidents)} incidents from {args.input_file}")

    # Skip already-embedded
    to_embed = [i for i in incidents if "embedding" not in i or i["embedding"] is None]
    already = len(incidents) - len(to_embed)
    if already > 0:
        logger.info(f"Skipping {already} already-embedded incidents")
    logger.info(f"Generating embeddings for {len(to_embed)} incidents")

    # Initialize OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY required")
    client = OpenAI(api_key=api_key)

    # Validate and truncate texts (8191 token limit ≈ 32K chars)
    MAX_CHARS = 30000  # Safe margin under 8191 tokens
    truncated = 0
    for inc in to_embed:
        if not inc.get("embedding_text"):
            inc["embedding_text"] = inc.get("cleaned_text") or inc.get("short_description", "")
        if len(inc["embedding_text"]) > MAX_CHARS:
            inc["embedding_text"] = inc["embedding_text"][:MAX_CHARS]
            truncated += 1
    if truncated:
        logger.info(f"Truncated {truncated} incidents to {MAX_CHARS} chars")

    # Generate in batches
    batch_size = min(args.batch_size, OPENAI_BATCH_LIMIT)
    total_tokens = 0
    start_time = time.time()

    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i:i + batch_size]
        texts = [inc["embedding_text"] for inc in batch]

        try:
            embeddings = get_embeddings_batch(client, texts)

            for inc, emb in zip(batch, embeddings):
                inc["embedding"] = emb

            batch_tokens = sum(len(t) // 4 for t in texts)  # rough estimate
            total_tokens += batch_tokens

            pct = min(100, (i + len(batch)) * 100 // len(to_embed))
            elapsed = time.time() - start_time
            rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
            eta = (len(to_embed) - i - len(batch)) / rate if rate > 0 else 0
            logger.info(
                f"  Batch {i // batch_size + 1}: {i + len(batch)}/{len(to_embed)} "
                f"({pct}%) | {rate:.0f} inc/s | ETA: {eta:.0f}s"
            )

        except Exception as e:
            logger.error(f"Batch failed at offset {i}: {e}")
            # Mark failed ones
            for inc in batch:
                inc["embedding"] = None
            time.sleep(5)  # back off on rate limit

    # Stats
    embedded_count = sum(1 for inc in incidents if inc.get("embedding") is not None)
    elapsed = time.time() - start_time
    est_cost = total_tokens / 1_000_000 * 0.02  # $0.02 per 1M tokens

    logger.info(f"\n{'='*60}")
    logger.info(f"EMBEDDING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Embedded:     {embedded_count}/{len(incidents)}")
    logger.info(f"Time:         {elapsed:.1f}s ({elapsed/60:.1f}m)")
    logger.info(f"Est. tokens:  {total_tokens:,}")
    logger.info(f"Est. cost:    ${est_cost:.4f}")

    # Save
    output_path = args.output or args.input_file.replace(".json", "_embedded.json")
    with open(output_path, "w") as f:
        json.dump(incidents, f, default=str)  # No indent — saves ~40% file size

    file_size_mb = os.path.getsize(output_path) / 1024 / 1024
    logger.info(f"Saved to:     {output_path} ({file_size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
