"""
Stage 1: retrieve.

Before planning anything, ask "what do we already know about this
project, and how reliable have its sources been?" On a project's first
episode ever, this returns empty lists -- the planner (stage 2) must
treat that as normal, not as an error.
"""
from __future__ import annotations

from src.agent.bedrock_client import embed_text
from src.agent.config import Config, RetrievedMemory
from src.db.connection import get_connection
from src.db.repository import get_sources_for_project, retrieve_similar_claims, retrieve_similar_lessons


def retrieve_memory(config: Config, project: str, query: str) -> RetrievedMemory:
    query_embedding = embed_text(config, query)

    with get_connection(config) as conn:
        with conn.cursor() as cur:
            claims = retrieve_similar_claims(cur, project, query_embedding)
            lessons = retrieve_similar_lessons(cur, project, query_embedding)
            sources = get_sources_for_project(cur, project)

    return RetrievedMemory(
        relevant_claims=claims,
        relevant_lessons=lessons,
        source_reliability=sources,
    )
