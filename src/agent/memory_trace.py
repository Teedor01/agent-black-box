from __future__ import annotations

from dataclasses import asdict

from src.agent.config import Config
from src.mcp.client import MCPClient
from src.mcp.reads import (
    get_sources_for_project,
    list_recent_contradictions,
    list_recent_episodes,
    list_recent_lessons,
)


def get_memory_trace(config: Config, project: str) -> dict:
    client = MCPClient(config.mcp_endpoint, config.mcp_bearer_token, config.mcp_database, config.mcp_cluster_id)

    sources = get_sources_for_project(client, project)
    episodes = list_recent_episodes(client, project)
    lessons = list_recent_lessons(client, project)
    contradictions = list_recent_contradictions(client, project)

    return {
        "project": project,
        "sources": [asdict(s) for s in sources],
        "episodes": episodes,
        "lessons": lessons,
        "contradictions": contradictions,
    }
