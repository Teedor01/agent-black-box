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
    mcp_database: str
    mcp_cluster_id: str = ""

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
                "COCKROACHDB_MCP_DATABASE",
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
            mcp_database=os.environ["COCKROACHDB_MCP_DATABASE"],
            mcp_cluster_id=os.environ.get("COCKROACHDB_MCP_CLUSTER_ID", ""),
        )


def new_id() -> str:
    
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
