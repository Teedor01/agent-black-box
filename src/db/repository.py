"""
Repository functions -- one function per read/write the agent loop needs.
No ORM: the schema is six tables and the queries are simple enough that an
ORM would add indirection without buying anything, matching the
architecture doc's "avoid unnecessary complexity" rule.
"""
from __future__ import annotations

from typing import Optional

from src.agent.config import EpisodeResult, SourceRecord, new_id, now


# ---------------------------------------------------------------------------
# Reads -- used by the retrieve stage
# ---------------------------------------------------------------------------

def get_sources_for_project(cur, project: str) -> list[SourceRecord]:
    cur.execute(
        """
        SELECT source_id, url, domain, source_type, project,
               reliability_score, times_used, successful_uses, problematic_uses
        FROM sources
        WHERE project = %s
        """,
        (project,),
    )
    return [
        SourceRecord(
            source_id=str(row[0]), url=row[1], domain=row[2], source_type=row[3],
            project=row[4], reliability_score=row[5], times_used=row[6],
            successful_uses=row[7], problematic_uses=row[8],
        )
        for row in cur.fetchall()
    ]


def retrieve_similar_claims(cur, project: str, query_embedding: list[float], limit: int = 5) -> list[dict]:
    """The structural-filter-then-vector-rank query from architecture doc
    Section F, using the (project, embedding) prefix-partitioned vector
    index -- only searches this project's partition, not the whole table."""
    cur.execute(
        """
        SELECT claim_id, text, confidence, source_id, superseded_by
        FROM claims
        WHERE project = %s AND superseded_by IS NULL
        ORDER BY embedding <-> %s
        LIMIT %s
        """,
        (project, str(query_embedding), limit),
    )
    return [
        {"claim_id": str(r[0]), "text": r[1], "confidence": r[2],
         "source_id": str(r[3]) if r[3] else None, "superseded_by": r[4]}
        for r in cur.fetchall()
    ]


def retrieve_similar_lessons(cur, project: str, query_embedding: list[float], limit: int = 5) -> list[dict]:
    cur.execute(
        """
        SELECT lesson_id, text, confidence, source_id
        FROM lessons
        WHERE project = %s
        ORDER BY embedding <-> %s
        LIMIT %s
        """,
        (project, str(query_embedding), limit),
    )
    return [
        {"lesson_id": str(r[0]), "text": r[1], "confidence": r[2],
         "source_id": str(r[3]) if r[3] else None}
        for r in cur.fetchall()
    ]


# ---------------------------------------------------------------------------
# Writes -- used by the persist stage. All of these are called from a
# single run_in_transaction() invocation in the orchestrator -- one
# episode's writes commit together or not at all.
# ---------------------------------------------------------------------------

def insert_episode(cur, episode_id: str, project: str, query: str, strategy: str) -> None:
    cur.execute(
        """
        INSERT INTO episodes (episode_id, project, query, strategy, status, started_at)
        VALUES (%s, %s, %s, %s, 'in_progress', %s)
        ON CONFLICT (episode_id) DO NOTHING
        """,
        (episode_id, project, query, strategy, now()),
    )


def complete_episode(cur, episode_id: str, final_answer: str) -> None:
    cur.execute(
        """
        UPDATE episodes
        SET status = 'completed', completed_at = %s, final_answer = %s
        WHERE episode_id = %s
        """,
        (now(), final_answer, episode_id),
    )


def link_episode_source(cur, episode_id: str, source_id: str, role: str) -> None:
    cur.execute(
        """
        INSERT INTO episode_sources (episode_id, source_id, role)
        VALUES (%s, %s, %s)
        ON CONFLICT (episode_id, source_id) DO UPDATE SET role = EXCLUDED.role
        """,
        (episode_id, source_id, role),
    )


def insert_claim(cur, episode_id: str, source_id: str, project: str, text: str,
                  embedding: list[float], confidence: float) -> str:
    claim_id = new_id()
    cur.execute(
        """
        INSERT INTO claims (claim_id, episode_id, source_id, project, text, embedding, confidence, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (claim_id, episode_id, source_id, project, text, str(embedding), confidence, now()),
    )
    return claim_id


def mark_claim_superseded(cur, old_claim_id: str, new_claim_id: str) -> None:
    """Append-only correction: never overwrite or delete the old claim,
    point it forward instead (architecture doc Section 5)."""
    cur.execute(
        "UPDATE claims SET superseded_by = %s WHERE claim_id = %s",
        (new_claim_id, old_claim_id),
    )


def insert_lesson(cur, episode_id: str, source_id: Optional[str], project: str,
                   text: str, embedding: list[float], confidence: float) -> str:
    lesson_id = new_id()
    cur.execute(
        """
        INSERT INTO lessons (lesson_id, episode_id, source_id, project, text, embedding, confidence, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (lesson_id, episode_id, source_id, project, text, str(embedding), confidence, now()),
    )
    return lesson_id


def insert_contradiction(cur, claim_id: str, conflicting_claim_id: str, note: str) -> None:
    cur.execute(
        """
        INSERT INTO contradictions (contradiction_id, claim_id, conflicting_claim_id, detected_at, resolution_note)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (new_id(), claim_id, conflicting_claim_id, now(), note),
    )


def update_source_reliability(cur, source_id: str, new_score: float,
                               times_used_delta: int, successful_delta: int,
                               problematic_delta: int) -> None:
    cur.execute(
        """
        UPDATE sources
        SET reliability_score = %s,
            times_used = times_used + %s,
            successful_uses = successful_uses + %s,
            problematic_uses = problematic_uses + %s,
            last_evaluated = %s
        WHERE source_id = %s
        """,
        (new_score, times_used_delta, successful_delta, problematic_delta, now(), source_id),
    )


def persist_episode(cur, result: EpisodeResult, source_roles: dict[str, str],
                     supersedes: dict[str, str], reliability_updates: list[dict]) -> None:
    """Single entry point the orchestrator calls inside run_in_transaction.
    source_roles: {source_id: 'used'|'rejected'|'deprioritized'}
    supersedes: {new_claim_id: old_claim_id} for any contradictions resolved this episode
    reliability_updates: [{'source_id', 'new_score', 'times_used_delta', 'successful_delta', 'problematic_delta'}]
    """
    insert_episode(cur, result.episode_id, result.project, result.query, result.strategy_summary)

    for source_id, role in source_roles.items():
        link_episode_source(cur, result.episode_id, source_id, role)

    claim_ids_by_text = {}
    for claim in result.claims:
        claim_id = insert_claim(
            cur, result.episode_id, claim.source_id, result.project,
            claim.text, claim.embedding, claim.confidence,
        )
        claim_ids_by_text[claim.text] = claim_id

    for new_claim_id, old_claim_id in supersedes.items():
        mark_claim_superseded(cur, old_claim_id, new_claim_id)

    for lesson in result.lessons:
        insert_lesson(cur, result.episode_id, lesson.source_id, result.project,
                       lesson.text, lesson.embedding, lesson.confidence)

    for update in reliability_updates:
        update_source_reliability(
            cur, update["source_id"], update["new_score"],
            update["times_used_delta"], update["successful_delta"], update["problematic_delta"],
        )

    complete_episode(cur, result.episode_id, result.final_answer)
