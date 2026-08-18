from __future__ import annotations

import json
import logging

import boto3

from src.agent.config import Config

logger = logging.getLogger(__name__)


class LLMResponseError(RuntimeError):
    pass


def get_bedrock_client(config: Config):
    return boto3.client("bedrock-runtime", region_name=config.aws_region)


def generate_text(config: Config, system_prompt: str, user_prompt: str,
                   max_tokens: int = 1024) -> str:
    client = get_bedrock_client(config)
    response = client.converse(
        modelId=config.bedrock_text_model_id,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        inferenceConfig={"maxTokens": max_tokens},
    )

    message = response.get("output", {}).get("message", {})
    content_blocks = message.get("content", [])
    stop_reason = response.get("stopReason")

    text_parts = [block["text"] for block in content_blocks if "text" in block]
    text = "".join(text_parts)

    if not text:
        diag = (
            f"generate_text: no text content in Bedrock response "
            f"(stop_reason={stop_reason}, {len(content_blocks)} block(s), "
            f"block keys={[list(b.keys()) for b in content_blocks]})."
        )
        logger.error(diag + " full_content=%s", content_blocks)
        raise LLMResponseError(diag)

    if stop_reason == "max_tokens":
        logger.warning(
            "generate_text: response was truncated by max_tokens=%d -- "
            "output may be incomplete JSON.",
            max_tokens,
        )

    return text


def strip_json_fence(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        stripped = "\n".join(lines).strip()
    return stripped


def parse_json_response(raw: str, context: str) -> dict
    cleaned = strip_json_fence(raw)
    try:
        obj, _ = json.JSONDecoder().raw_decode(cleaned)
        return obj
    except json.JSONDecodeError as exc:
        diag = (
            f"{context}: failed to parse model output as JSON "
            f"(raw_len={len(raw)}). Raw (truncated): {raw[:300]!r}"
        )
        logger.error(diag)
        raise LLMResponseError(diag) from exc


def embed_text(config: Config, text: str) -> list[float]:
    client = get_bedrock_client(config)
    response = client.invoke_model(
        modelId=config.bedrock_embedding_model_id,
        body=json.dumps({"inputText": text}),
        contentType="application/json",
        accept="application/json",
    )
    raw = response["body"].read()

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        diag = (
            f"embed_text: Titan embedding response was not valid JSON "
            f"(raw_len={len(raw)}). Raw (truncated): {raw[:300]!r}"
        )
        logger.error(diag)
        raise LLMResponseError(diag) from exc

    if "embedding" not in body:
        diag = (
            f"embed_text: Titan response had no 'embedding' key. "
            f"Keys present: {list(body.keys())}. Body (truncated): {str(body)[:300]!r}"
        )
        logger.error(diag)
        raise LLMResponseError(diag)

    return body["embedding"]
