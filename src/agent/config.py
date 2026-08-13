"""
Shared configuration and dataclasses for the Agent Black Box loop.

Every stage module (memory, planner, sources, extractor, learner,
orchestrator) imports from here rather than reading os.environ directly,
so there's exactly one place that knows about env var names.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    cockroachdb_connection_string: str
    aws_region: str
    bedrock_embedding_model_id: str
    bedrock_text_model_id: str
    mcp_endpoint: str
    mcp_bearer_token: str

    @classmethod
    def from_env(cls) -> "Config":
        missing = [
            name
            for name in (
                "COCKROACHDB_CONNECTION_STRING",
                "AWS_REGION",
                "BEDROCK_EMBEDDING_MODEL_ID",
                "BEDROCK_TEXT_MODEL_ID",
                "COCKROACHDB_MCP_ENDPOINT",
                "COCKROACHDB_MCP_BEARER_TOKEN",
            )
            if not os.environ.get(name)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill in real values."
            )
        return cls(
            cockroachdb_connection_string=os.environ["COCKROACHDB_CONNECTION_STRING"],
            aws_region=os.environ["AWS_REGION"],
            bedrock_embedding_model_id=os.environ["BEDROCK_EMBEDDING_MODEL_ID"],
            bedrock_text_model_id=os.environ["BEDROCK_TEXT_MODEL_ID"],
            mcp_endpoint=os.environ["COCKROACHDB_MCP_ENDPOINT"],
            mcp_bearer_token=os.environ["COCKROACHDB_MCP_BEARER_TOKEN"],
        )


def new_id() -> str:
    """Client-generated UUID. Generating IDs client-side (rather than
    relying on gen_random_uuid() server-side) is what makes episode writes
    idempotent on retry -- see Section on reliability in the architecture
    doc: a retried write with the same episode_id is a no-op, not a
    duplicate."""
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SourceRecord:
    source_id: str
    url: str
    domain: str
    source_type: str
    project: str
    reliability_score: float
    times_used: int
    successful_uses: int
    problematic_uses: int


@dataclass
class RetrievedMemory:
    """What the retrieve stage hands to the planner. Empty on a project's
    first-ever episode -- the planner must handle that gracefully rather
    than assuming history exists."""

    relevant_claims: list[dict] = field(default_factory=list)
    relevant_lessons: list[dict] = field(default_factory=list)
    source_reliability: list[SourceRecord] = field(default_factory=list)


@dataclass
class PlannedSource:
    source_id: str
    url: str
    domain: str
    priority: int
    rationale: str


@dataclass
class ResearchPlan:
    strategy_summary: str
    planned_sources: list[PlannedSource]


@dataclass
class ExtractedClaim:
    text: str
    confidence: float
    embedding: list[float]
    source_id: str
    claim_id: str = field(default_factory=new_id)


@dataclass
class Lesson:
    text: str
    confidence: float
    embedding: list[float]
    source_id: Optional[str]


@dataclass
class EpisodeResult:
    episode_id: str
    project: str
    query: str
    strategy_summary: str
    claims: list[ExtractedClaim]
    lessons: list[Lesson]
    final_answer: str
    status: str = "completed"
