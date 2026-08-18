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

BUG FIXED (earlier): embeddings were being stringified with plain
str(), which uses Python's full ~17-digit float repr per value. For a
1024-dim embedding that produces a query string long enough to exceed
the select_query tool's confirmed 16384-character QUERY limit.
_vector_literal() below formats each value to 6 decimal places instead.

BUG FIXED 2026-08-16: list_recent_episodes selected full strategy and
final_answer text columns (each can run 1000-2000+ characters once a
real episode's plan/answer text is that detailed) at LIMIT 10 -- once
enough real episodes existed, this exceeded a separate, smaller
RESULT-size cap on the select_query tool (confirmed via the real error:
"executing select query: executing stmt 1: max result size exceeded",
pinpointed to this specific query via memory_trace.py's per-call
diagnostics rather than guessed). Fixed by truncating the large text
columns with SQL LEFT() and lowering LIMIT -- the Memory Trace view is
a browsable overview, not a full transcript, so this is a reasonable
scope for the list view rather than a workaround. Applied the same
truncation preventively to lessons/contradictions text, since those
will only grow between now and the deadline.
"""
from __future__ import annotations

from src.agent.config import SourceRecord
from src.mcp.client import MCPClient

# Character cap for text columns in LIST views only (Memory Trace
# overview) -- NOT applied to claims/lessons used for actual retrieval
# during an episode's plan stage, which need full text to reason over.
LIST_VIEW_TEXT_TRUNCATE = 300


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
    # Full, untruncated text -- this feeds the planner's actual
    # reasoning during an episode, unlike the LIST_VIEW_TEXT_TRUNCATE
    # queries below which are for the human-facing overview only.
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
    # Same note as retrieve_similar_claims -- full text, feeds real
    # agent reasoning, not truncated.
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
# activity for this project" queries -- no embedding involved. Text
# columns are truncated with LEFT() since this is an overview list, not
# a full-detail view, and the untruncated version hit the MCP tool's
# result-size cap once real data accumulated (see module docstring).

def list_recent_episodes(client: MCPClient, project: str, limit: int = 5) -> list[dict]:
    return client.execute_sql(
        f"""
        SELECT episode_id, query, LEFT(strategy, {LIST_VIEW_TEXT_TRUNCATE}) AS strategy,
               status, started_at, completed_at,
               LEFT(final_answer, {LIST_VIEW_TEXT_TRUNCATE}) AS final_answer
        FROM episodes
        WHERE project = $1
        ORDER BY started_at DESC
        LIMIT $2
        """,
        [project, limit],
    )


def list_recent_lessons(client: MCPClient, project: str, limit: int = 10) -> list[dict]:
    return client.execute_sql(
        f"""
        SELECT lesson_id, LEFT(text, {LIST_VIEW_TEXT_TRUNCATE}) AS text,
               confidence, source_id, created_at
        FROM lessons
        WHERE project = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        [project, limit],
    )


def list_recent_contradictions(client: MCPClient, project: str, limit: int = 10) -> list[dict]:
    """Joins back to claims so the UI can show what changed, not just
    opaque IDs -- this is the single view that most directly proves the
    "agent remembers and corrects itself" claim to a judge."""
    return client.execute_sql(
        f"""
        SELECT c.contradiction_id, c.detected_at,
               LEFT(c.resolution_note, {LIST_VIEW_TEXT_TRUNCATE}) AS resolution_note,
               LEFT(new_claim.text, {LIST_VIEW_TEXT_TRUNCATE}) AS new_claim_text,
               LEFT(old_claim.text, {LIST_VIEW_TEXT_TRUNCATE}) AS old_claim_text,
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
