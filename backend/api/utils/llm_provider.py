"""
REX-US — LLM Provider Abstraction

Two providers, switchable via LLM_PROVIDER env var:

  openai  (default) — uses OpenAI SDK with API key. For local development.
  bedrock — uses boto3 bedrock-runtime SDK with IAM role. For production on AWS.

Configuration:
  LLM_PROVIDER=openai|bedrock
  LLM_CHAT_MODEL=gpt-4o                         (or anthropic.claude-opus-4-6-v1)
  LLM_EMBED_MODEL=text-embedding-3-small         (or amazon.titan-embed-text-v2)
  OPENAI_API_KEY=sk-...                           (required when LLM_PROVIDER=openai)
  AWS_REGION=us-east-1                            (required when LLM_PROVIDER=bedrock)

All routers import from this module. No router creates its own LLM client.
"""

import os
import json
import logging
import asyncio
import warnings
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────

LLM_PROVIDER   = os.getenv("LLM_PROVIDER",   "openai")
LLM_CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", "gpt-4o")
LLM_EMBED_MODEL = os.getenv("LLM_EMBED_MODEL", "text-embedding-3-small")
AWS_REGION     = os.getenv("AWS_REGION",     "us-west-2")

# Bedrock inference profile ARNs  (used as modelId instead of plain model strings)
BEDROCK_CHAT_MODEL_ID  = os.getenv(
    "BEDROCK_CHAT_MODEL_ID",
    "arn:aws:bedrock:us-west-2:288761730964:application-inference-profile/yptc9mo9d8it",
)
BEDROCK_EMBED_MODEL_ID = os.getenv(
    "BEDROCK_EMBED_MODEL_ID",
    "arn:aws:bedrock:us-west-2:288761730964:application-inference-profile/o1pfx36i19zl",
)

# IAM role to assume before calling Bedrock (leave blank to use the task's own role)
BEDROCK_ROLE_ARN = os.getenv(
    "BEDROCK_ROLE_ARN",
    "arn:aws:iam::288761730964:role/dt-rexus-stg",
)

# Embed request body format: "titan" | "cohere" (default)
# Use "titan" for amazon.titan-embed-* models (body: {"inputText": "..."})
# Use "cohere" for cohere.embed-* models     (body: {"texts": [...], "input_type": "..."})
BEDROCK_EMBED_MODEL_TYPE = os.getenv("BEDROCK_EMBED_MODEL_TYPE", "cohere")


# ═══════════════════════════════════════════════════════════════════
# Bedrock Provider (boto3) — for AWS production
# ═══════════════════════════════════════════════════════════════════

_boto_client = None
_boto_client_expiry = None  # datetime when the assumed-role credentials expire


def _get_boto_client():
    """Lazy-init boto3 bedrock-runtime client.

    If BEDROCK_ROLE_ARN is set the client assumes that IAM role via STS first
    and uses the resulting temporary credentials.  Credentials are refreshed
    automatically 5 minutes before they expire (default session = 1 h).
    """
    global _boto_client, _boto_client_expiry
    import boto3
    from datetime import datetime, timezone, timedelta

    # Refresh if credentials are about to expire (within 5 minutes)
    needs_refresh = (
        _boto_client is None
        or (
            BEDROCK_ROLE_ARN
            and _boto_client_expiry is not None
            and datetime.now(timezone.utc) >= _boto_client_expiry - timedelta(minutes=5)
        )
    )

    if needs_refresh:
        if BEDROCK_ROLE_ARN:
            logger.info("Assuming Bedrock role: %s", BEDROCK_ROLE_ARN)
            sts = boto3.client("sts", region_name=AWS_REGION)
            response = sts.assume_role(
                RoleArn=BEDROCK_ROLE_ARN,
                RoleSessionName="rexus-bedrock-session",
                DurationSeconds=3600,
            )
            creds = response["Credentials"]
            _boto_client_expiry = creds["Expiration"]
            _boto_client = boto3.client(
                "bedrock-runtime",
                region_name=AWS_REGION,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
            logger.info(
                "Bedrock client initialised via assumed role (region=%s, expires=%s)",
                AWS_REGION, _boto_client_expiry.isoformat(),
            )
        else:
            _boto_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
            logger.info("Bedrock client initialised with task role (region=%s)", AWS_REGION)

    return _boto_client


async def _bedrock_chat(model, messages, max_tokens=1500, temperature=0.1):
    """Chat completion via boto3 invoke_model. Supports Anthropic Claude models."""
    client = _get_boto_client()

    system_parts = []
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            chat_messages.append({"role": msg["role"], "content": msg["content"]})

    if "anthropic" in model.lower():
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
    else:
        body = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

    response = await asyncio.to_thread(
        client.invoke_model,
        modelId=model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )

    result = json.loads(response["body"].read())

    if "anthropic" in model.lower():
        content = result.get("content", [{}])
        text = content[0].get("text", "") if content else ""
        input_tokens = result.get("usage", {}).get("input_tokens", 0)
        output_tokens = result.get("usage", {}).get("output_tokens", 0)
    else:
        text = result.get("output", result.get("completion", ""))
        input_tokens = result.get("usage", {}).get("input_tokens", 0)
        output_tokens = result.get("usage", {}).get("output_tokens", 0)

    return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)


async def _bedrock_embed(model, text):
    """Generate embedding via boto3 invoke_model.

    Body format is determined by BEDROCK_EMBED_MODEL_TYPE (not the model ARN,
    which may be an opaque inference profile and contain no model family hint):
      titan  — {"inputText": "..."}                (amazon.titan-embed-*)
      cohere — {"texts": [...], "input_type": ...}  (cohere.embed-*)
    """
    client = _get_boto_client()

    model_type = BEDROCK_EMBED_MODEL_TYPE.lower()

    if model_type == "cohere":
        body = {"texts": [text], "input_type": "search_document"}
    else:
        # Default: titan
        body = {"inputText": text}

    response = await asyncio.to_thread(
        client.invoke_model,
        modelId=model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )

    result = json.loads(response["body"].read())

    logger.debug(
        "_bedrock_embed response | model=%s model_type=%s top_keys=%s",
        model, model_type, list(result.keys()),
    )

    if model_type == "cohere":
        # Cohere Embed v3 returns: {"embeddings": [[float, ...]]}
        # Cohere Embed v4 returns: {"embeddings": {"float": [[float, ...]]}}
        embeddings = result.get("embeddings", [])
        logger.debug(
            "_bedrock_embed cohere | embeddings type=%s keys=%s",
            type(embeddings).__name__,
            list(embeddings.keys()) if isinstance(embeddings, dict) else f"list[{len(embeddings)}]",
        )
        if isinstance(embeddings, dict):
            # v4 format
            float_embeddings = embeddings.get("float", [[]])
            logger.debug("_bedrock_embed cohere v4 | float vectors=%d dim=%d",
                         len(float_embeddings),
                         len(float_embeddings[0]) if float_embeddings else 0)
            return float_embeddings[0] if float_embeddings else []
        else:
            # v3 format
            logger.debug("_bedrock_embed cohere v3 | vectors=%d dim=%d",
                         len(embeddings),
                         len(embeddings[0]) if embeddings else 0)
            return embeddings[0] if embeddings else []
    else:
        # titan returns {"embedding": [...], "inputTextTokenCount": N}
        embedding = result.get("embedding", [])
        logger.debug("_bedrock_embed titan | dim=%d tokens=%s",
                     len(embedding),
                     result.get("inputTextTokenCount", "?"))
        return embedding


# ═══════════════════════════════════════════════════════════════════
# OpenAI Provider — for local development
# ═══════════════════════════════════════════════════════════════════

_openai_client = None


def _get_openai_client():
    """Lazy-init OpenAI client."""
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning(
                "OPENAI_API_KEY is not set — LLM features will not work. "
                "Set LLM_PROVIDER=bedrock for AWS production deployments."
            )
        _openai_client = AsyncOpenAI(api_key=api_key)
        logger.info(f"OpenAI client initialized")
    return _openai_client


async def _openai_chat(model, messages, max_tokens=1500, temperature=0.1):
    """Chat completion via OpenAI SDK."""
    client = _get_openai_client()
    try:
        return await client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
        )
    except Exception as e:
        if "max_tokens" in str(e) and "max_completion_tokens" in str(e):
            return await client.chat.completions.create(
                model=model, messages=messages,
                max_completion_tokens=max_tokens, temperature=max(temperature, 1.0),
            )
        raise


async def _openai_embed(model, text):
    """Generate embedding via OpenAI SDK."""
    client = _get_openai_client()
    resp = await client.embeddings.create(model=model, input=text)
    return resp.data[0].embedding


# ═══════════════════════════════════════════════════════════════════
# Normalized response wrapper (so boto responses look like OpenAI)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class LLMResponse:
    """Normalized LLM response wrapper — provides a unified interface matching
    the OpenAI SDK response shape for both OpenAI and Bedrock providers."""
    text: str
    input_tokens: int
    output_tokens: int

    @property
    def choices(self):
        return [self]

    @property
    def message(self):
        return self

    @property
    def content(self):
        return self.text

    @property
    def usage(self):
        return self

    @property
    def prompt_tokens(self):
        return self.input_tokens

    @property
    def completion_tokens(self):
        return self.output_tokens

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens


# ═══════════════════════════════════════════════════════════════════
# Public API — all routers use these functions
# ═══════════════════════════════════════════════════════════════════

def get_chat_model() -> str:
    return LLM_CHAT_MODEL


def get_embed_model() -> str:
    return LLM_EMBED_MODEL


async def embed_text(text: str) -> list[float]:
    """Generate embedding for a single text."""
    if LLM_PROVIDER == "bedrock":
        return await _bedrock_embed(BEDROCK_EMBED_MODEL_ID, text)
    return await _openai_embed(LLM_EMBED_MODEL, text)


async def chat_complete(messages: list[dict], max_tokens: int = 1500, temperature: float = 0.1):
    """
    Run a chat completion. Returns an object with:
      .choices[0].message.content  — the generated text
      .usage.prompt_tokens         — input tokens
      .usage.completion_tokens     — output tokens
    Works identically for both providers.
    """
    if LLM_PROVIDER == "bedrock":
        return await _bedrock_chat(BEDROCK_CHAT_MODEL_ID, messages, max_tokens, temperature)
    return await _openai_chat(LLM_CHAT_MODEL, messages, max_tokens, temperature)


def get_provider_info() -> dict:
    """Return current provider configuration (for health check / admin)."""
    info = {
        "provider": LLM_PROVIDER,
        "chat_model": LLM_CHAT_MODEL,
        "embed_model": LLM_EMBED_MODEL,
        "environment": os.getenv("REXUS_ENV", "development"),
    }
    if LLM_PROVIDER == "bedrock":
        info["region"] = AWS_REGION
        info["chat_model"] = BEDROCK_CHAT_MODEL_ID
        info["embed_model"] = BEDROCK_EMBED_MODEL_ID
        info["role_arn"] = BEDROCK_ROLE_ARN or "task-role (no assume)"
    return info
