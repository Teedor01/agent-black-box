"""
Thin wrapper around boto3's bedrock-runtime client. Two calls only:
generate_text (Claude Sonnet 5, via Converse) and embed_text (Titan
embeddings). No agent framework wraps this -- the orchestrator calls
these functions directly at each stage, which is what keeps the
retrieve -> plan -> act -> evaluate -> learn -> persist loop visible
rather than hidden inside a managed agent runtime (architecture doc's
explicit reason for rejecting Bedrock Agents).
"""
from __future__ import annotations

import json

import boto3

from src.agent.config import Config


def get_bedrock_client(config: Config):
    return boto3.client("bedrock-runtime", region_name=config.aws_region)


def generate_text(config: Config, system_prompt: str, user_prompt: str,
                   max_tokens: int = 1024) -> str:
    """Calls Claude Sonnet 5 via the Converse API. Verified model ID:
    anthropic.claude-sonnet-5 (no date suffix, no ARN-versioned form --
    see infra/SETUP.md for how this was confirmed against the AWS Bedrock
    model catalog)."""
    client = get_bedrock_client(config)
    response = client.converse(
        modelId=config.bedrock_text_model_id,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        inferenceConfig={"maxTokens": max_tokens},
    )
    return response["output"]["message"]["content"][0]["text"]


def embed_text(config: Config, text: str) -> list[float]:
    """Calls the Titan embedding model. Output dimension MUST match the
    VECTOR(...) size declared in src/db/schema.sql -- see the Day 1 setup
    checklist for why this is a gate, not an afterthought."""
    client = get_bedrock_client(config)
    response = client.invoke_model(
        modelId=config.bedrock_embedding_model_id,
        body=json.dumps({"inputText": text}),
        contentType="application/json",
        accept="application/json",
    )
    body = json.loads(response["body"].read())
    return body["embedding"]
