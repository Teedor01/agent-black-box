from __future__ import annotations

from src.agent.bedrock_client import embed_text
from src.agent.config import Config, RetrievedMemory
from src.mcp.client import MCPClient
from src.mcp.reads import get_sources_for_project, retrieve_similar_claims, retrieve_similar_lessons


def retrieve_memory(config: Config, project: str, query: str) -> RetrievedMemory:
    query_embedding = embed_text(config, query)

    client = MCPClient(config.mcp_endpoint, config.mcp_bearer_token, config.mcp_database, config.mcp_cluster_id)

    claims = retrieve_similar_claims(client, project, query_embedding)
    lessons = retrieve_similar_lessons(client, project, query_embedding)
    sources = get_sources_for_project(client, project)

    return RetrievedMemory(
        relevant_claims=claims,
        relevant_lessons=lessons,
        source_reliability=sources,
    )
