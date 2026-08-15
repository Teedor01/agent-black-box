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
prepared statement syntax -- confirmed working against the real server.

BUG FIXED HERE: embeddings were being stringified with plain str(),
which uses Python's full ~17-digit float repr per value. For a 1024-dim
embedding that produces a query string long enough to exceed the
select_query tool's confirmed 16384-character limit. _vector_literal()
below formats each value to 6 decimal places instead -- far more
precision than a similarity search needs, and comfortably under the
limit.
"""
from __future__ import annotations

from src.agent.config import SourceRecord
from src.mcp.client import MCPClient


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"


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
        [project, _vector_literal(query_embedding), limit],
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
        [project, _vector_literal(query_embedding), limit],
    )
    return [
        {"lesson_id": str(r["lesson_id"]), "text": r["text"], "confidence": r["confidence"],
         "source_id": str(r["source_id"]) if r.get("source_id") else None}
        for r in rows
    ]


# --- Below: list queries for the Memory Trace view (Day 7). Unlike the
# vector-ranked retrieval above, these are plain "show me recent
# activity for this project" queries -- no embedding involved.

def list_recent_episodes(client: MCPClient, project: str, limit: int = 10) -> list[dict]:
    return client.execute_sql(
        """
        SELECT episode_id, query, strategy, status, started_at, completed_at, final_answer
        FROM episodes
        WHERE project = $1
        ORDER BY started_at DESC
        LIMIT $2
        """,
        [project, limit],
    )


def list_recent_lessons(client: MCPClient, project: str, limit: int = 20) -> list[dict]:
    return client.execute_sql(
        """
        SELECT lesson_id, text, confidence, source_id, created_at
        FROM lessons
        WHERE project = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        [project, limit],
    )


def list_recent_contradictions(client: MCPClient, project: str, limit: int = 20) -> list[dict]:
    """Joins back to claims so the UI can show what changed, not just
    opaque IDs -- this is the single view that most directly proves the
    "agent remembers and corrects itself" claim to a judge."""
    return client.execute_sql(
        """
        SELECT c.contradiction_id, c.detected_at, c.resolution_note,
               new_claim.text AS new_claim_text,
               old_claim.text AS old_claim_text,
               old_claim.source_id AS old_source_id
        FROM contradictions c
        JOIN claims new_claim ON new_claim.claim_id = c.claim_id
        JOIN claims old_claim ON old_claim.claim_id = c.conflicting_claim_id
        WHERE new_claim.project = $1
        ORDER BY c.detected_at DESC
        LIMIT $2
        """,
        [project, limit],
    )
