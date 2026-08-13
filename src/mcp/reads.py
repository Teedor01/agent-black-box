"""
Read-only queries for the retrieve stage, issued through the MCP client
instead of psycopg -- this is what closes the gap flagged in Day 6: the
agent's own runtime reads now go through the read-only MCP credential,
distinct from the app backend's read/write psycopg credential used by
src/db/repository.py's writes at persist time.

Same SQL and table/column names as src/db/repository.py's read
functions -- deliberately kept parallel rather than sharing code, since
the two paths use genuinely different credentials and transports and
conflating them would blur the security boundary the architecture doc
asks for.

Parameter placeholder style ($1, $2, ...) matches Postgres-native
prepared statement syntax, since that's the most likely convention for a
generic SQL-execution MCP tool wrapping the Postgres wire protocol --
UNCONFIRMED against the real server, adjust if verify_mcp_connection.py
shows otherwise.
"""
from __future__ import annotations

from src.agent.config import SourceRecord
from src.mcp.client import MCPClient


def get_sources_for_project(client: MCPClient, project: str) -> list[SourceRecord]:
    rows = client.execute_sql(
        """
        SELECT source_id, url, domain, source_type, project,
               reliability_score, times_used, successful_uses, problematic_uses
        FROM sources
        WHERE project = $1
        """,
        [project],
    )
    return [
        SourceRecord(
            source_id=str(row["source_id"]), url=row["url"], domain=row["domain"],
            source_type=row["source_type"], project=row["project"],
            reliability_score=row["reliability_score"], times_used=row["times_used"],
            successful_uses=row["successful_uses"], problematic_uses=row["problematic_uses"],
        )
        for row in rows
    ]


def retrieve_similar_claims(client: MCPClient, project: str, query_embedding: list[float], limit: int = 5) -> list[dict]:
    rows = client.execute_sql(
        """
        SELECT claim_id, text, confidence, source_id, superseded_by
        FROM claims
        WHERE project = $1 AND superseded_by IS NULL
        ORDER BY embedding <-> $2
        LIMIT $3
        """,
        [project, str(query_embedding), limit],
    )
    return [
        {"claim_id": str(r["claim_id"]), "text": r["text"], "confidence": r["confidence"],
         "source_id": str(r["source_id"]) if r.get("source_id") else None,
         "superseded_by": r.get("superseded_by")}
        for r in rows
    ]


def retrieve_similar_lessons(client: MCPClient, project: str, query_embedding: list[float], limit: int = 5) -> list[dict]:
    rows = client.execute_sql(
        """
        SELECT lesson_id, text, confidence, source_id
        FROM lessons
        WHERE project = $1
        ORDER BY embedding <-> $2
        LIMIT $3
        """,
        [project, str(query_embedding), limit],
    )
    return [
        {"lesson_id": str(r["lesson_id"]), "text": r["text"], "confidence": r["confidence"],
         "source_id": str(r["source_id"]) if r.get("source_id") else None}
        for r in rows
    ]
