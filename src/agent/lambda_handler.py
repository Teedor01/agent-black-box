from __future__ import annotations

import base64
import json
import logging
import os
from typing import Optional

import boto3

from src.agent.config import Config
from src.agent.memory_trace import get_memory_trace
from src.agent.orchestrator import run_episode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agent_black_box.lambda")

_cached_config: Optional[Config] = None


def _get_secret(client, secret_arn: str, json_key: str) -> str:
    response = client.get_secret_value(SecretId=secret_arn)
    raw = response["SecretString"]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        diag = (
            f"_get_secret({secret_arn}): SecretString was not valid JSON "
            f"(raw_len={len(raw)}). Raw (truncated): {raw[:200]!r}"
        )
        log.error(diag)
        raise RuntimeError(diag) from exc

    if json_key not in parsed:
        diag = (
            f"_get_secret({secret_arn}): expected key {json_key!r} not found. "
            f"Keys present: {list(parsed.keys())}"
        )
        log.error(diag)
        raise RuntimeError(diag)

    return parsed[json_key]


def _load_config() -> Config:
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    region = os.environ["AWS_REGION"]
    secrets_client = boto3.client("secretsmanager", region_name=region)

    cockroachdb_connection_string = _get_secret(
        secrets_client, os.environ["SECRET_ARN_COCKROACHDB"], "DATABASE_URL",
    )
    mcp_bearer_token = _get_secret(
        secrets_client, os.environ["SECRET_ARN_MCP_TOKEN"], "MCP_BEARER_TOKEN",
    )

    _cached_config = Config(
        cockroachdb_connection_string=cockroachdb_connection_string,
        aws_region=region,
        bedrock_embedding_model_id=os.environ["BEDROCK_EMBEDDING_MODEL_ID"],
        bedrock_text_model_id=os.environ["BEDROCK_TEXT_MODEL_ID"],
        mcp_endpoint=os.environ["COCKROACHDB_MCP_ENDPOINT"],
        mcp_bearer_token=mcp_bearer_token,
        mcp_database=os.environ["COCKROACHDB_MCP_DATABASE"],
        mcp_cluster_id=os.environ.get("COCKROACHDB_MCP_CLUSTER_ID", ""),
    )
    return _cached_config


def _parse_event(event: dict) -> dict:
    body = event.get("body")
    if not isinstance(body, str):
        return event

    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception as exc:
            diag = f"_parse_event: failed to base64-decode event body (len={len(body)})."
            log.error(diag)
            raise RuntimeError(diag) from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        diag = (
            f"_parse_event: event body was not valid JSON "
            f"(isBase64Encoded={event.get('isBase64Encoded')}, len={len(body)}). "
            f"Raw (truncated): {body[:200]!r}"
        )
        log.error(diag)
        raise RuntimeError(diag) from exc


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event, context):
    try:
        payload = _parse_event(event)
    except RuntimeError as exc:
        return _response(400, {"error": str(exc)})

    action = payload.get("action", "run_episode")

    if action == "memory_trace":
        return _handle_memory_trace(payload)
    return _handle_run_episode(payload)


def _handle_memory_trace(payload: dict) -> dict:
    project = payload.get("project")
    if not project:
        return _response(400, {"error": "'project' is required."})

    try:
        config = _load_config()
        trace = get_memory_trace(config, project)
    except Exception as exc:
        log.exception("memory_trace failed project=%s", project)
        return _response(500, {"error": str(exc)})

    return _response(200, trace)


def _handle_run_episode(payload: dict) -> dict:
    project = payload.get("project")
    query = payload.get("query")
    episode_id = payload.get("episode_id")  

    if not project or not query:
        return _response(400, {"error": "Both 'project' and 'query' are required."})

    try:
        config = _load_config()
        result = run_episode(config, project=project, query=query, episode_id=episode_id)
    except Exception as exc:
        log.exception("episode failed project=%s query=%r", project, query)
        return _response(500, {"error": str(exc), "project": project, "query": query})

    return _response(200, {
        "episode_id": result.episode_id,
        "status": result.status,
        "strategy_summary": result.strategy_summary,
        "final_answer": result.final_answer,
        "claims": [{"text": c.text, "confidence": c.confidence, "source_id": c.source_id} for c in result.claims],
        "lessons": [{"text": l.text, "confidence": l.confidence, "source_id": l.source_id} for l in result.lessons],
    })
