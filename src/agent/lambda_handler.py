"""
AWS Lambda entry point wrapping run_episode(). Day 6.

Handler string for the Lambda configuration: src.agent.lambda_handler.handler
(the deployment package's root must be the repo root so `src` is importable
-- see scripts/package_lambda.py, which builds the zip that way).

Secrets: fetched once per cold start from AWS Secrets Manager using the
ARNs in SECRET_ARN_COCKROACHDB / SECRET_ARN_MCP_TOKEN environment
variables (set these to the ARNs in the Lambda config, not the secret
VALUES -- the execution role from infra/SETUP.md grants
secretsmanager:GetSecretValue scoped to exactly these two secrets).
Cached at module level so warm invocations skip the round trip.

The MCP bearer token fetched here is what src/agent/memory.py uses for
its read-only retrieve-stage queries via src/mcp/client.py -- the app
backend's read/write psycopg credential (cockroachdb_connection_string)
is only used by src/db/repository.py's writes at persist time.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import boto3

from src.agent.config import Config
from src.agent.orchestrator import run_episode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agent_black_box.lambda")

_cached_config: Optional[Config] = None


def _get_secret(client, secret_arn: str) -> str:
    response = client.get_secret_value(SecretId=secret_arn)
    return response["SecretString"]


def _load_config() -> Config:
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    region = os.environ["AWS_REGION"]
    secrets_client = boto3.client("secretsmanager", region_name=region)

    cockroachdb_connection_string = _get_secret(secrets_client, os.environ["SECRET_ARN_COCKROACHDB"])
    mcp_bearer_token = _get_secret(secrets_client, os.environ["SECRET_ARN_MCP_TOKEN"])

    _cached_config = Config(
        cockroachdb_connection_string=cockroachdb_connection_string,
        aws_region=region,
        bedrock_embedding_model_id=os.environ["BEDROCK_EMBEDDING_MODEL_ID"],
        bedrock_text_model_id=os.environ["BEDROCK_TEXT_MODEL_ID"],
        mcp_endpoint=os.environ["COCKROACHDB_MCP_ENDPOINT"],
        mcp_bearer_token=mcp_bearer_token,
    )
    return _cached_config


def _parse_event(event: dict) -> dict:
    """Supports a direct Lambda invoke payload and an API Gateway
    proxy-integration event (payload JSON-encoded in event['body'])."""
    if isinstance(event.get("body"), str):
        return json.loads(event["body"])
    return event


def _response(status_code: int, body: dict) -> dict:
    """API-Gateway-shaped response -- harmless if invoked directly
    (non-API Gateway) instead, since it's still just a dict."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event, context):
    payload = _parse_event(event)

    project = payload.get("project")
    query = payload.get("query")
    episode_id = payload.get("episode_id")  # optional: pass the same value on retry for idempotency

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
        "final_answer": result.final_answer,
        "claims_count": len(result.claims),
        "lessons_count": len(result.lessons),
    })
