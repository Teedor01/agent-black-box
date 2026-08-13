"""
Stage 1: retrieve.

Before planning anything, ask "what do we already know about this
project, and how reliable have its sources been?" On a project's first
episode ever, this returns empty lists -- the planner (stage 2) must
treat that as normal, not as an error.

Reads go through the CockroachDB Managed MCP Server (src/mcp/), using
the read-only bearer-token credential -- NOT psycopg, and NOT the app
backend's read/write credential. That split is the actual point of using
MCP here rather than just calling it "integrated" because it's imported
somewhere: the agent's own runtime reasoning reads memory through a
credential that cannot write, no matter what a bad prompt or a bug talks
it into attempting.
"""
from __future__ import annotations

from src.agent.bedrock_client import embed_text
from src.agent.config import Config, RetrievedMemory
from src.mcp.client import MCPClient
from src.mcp.reads import get_sources_for_project, retrieve_similar_claims, retrieve_similar_lessons


def retrieve_memory(config: Config, project: str, query: str) -> RetrievedMemory:
    query_embedding = embed_text(config, query)

    client = MCPClient(config.mcp_endpoint, config.mcp_bearer_token)

    claims = retrieve_similar_claims(client, project, query_embedding)
    lessons = retrieve_similar_lessons(client, project, query_embedding)
    sources = get_sources_for_project(client, project)

    return RetrievedMemory(
        relevant_claims=claims,
        relevant_lessons=lessons,
        source_reliability=sources,
    )
