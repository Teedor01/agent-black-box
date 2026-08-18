from __future__ import annotations

from dataclasses import asdict

from src.agent.config import Config
from src.mcp.client import MCPClient, MCPError
from src.mcp.reads import (
    get_sources_for_project,
    list_recent_contradictions,
    list_recent_episodes,
    list_recent_lessons,
)


def get_memory_trace(config: Config, project: str) -> dict:
    client = MCPClient(config.mcp_endpoint, config.mcp_bearer_token, config.mcp_database, config.mcp_cluster_id)

    try:
        sources = get_sources_for_project(client, project)
    except MCPError as exc:
        raise MCPError(f"get_sources_for_project failed: {exc}") from exc

    try:
        episodes = list_recent_episodes(client, project)
    except MCPError as exc:
        raise MCPError(f"list_recent_episodes failed: {exc}") from exc

    try:
        lessons = list_recent_lessons(client, project)
    except MCPError as exc:
        raise MCPError(f"list_recent_lessons failed: {exc}") from exc

    try:
        contradictions = list_recent_contradictions(client, project)
    except MCPError as exc:
        raise MCPError(f"list_recent_contradictions failed: {exc}") from exc

    return {
        "project": project,
        "sources": [asdict(s) for s in sources],
        "episodes": episodes,
        "lessons": lessons,
        "contradictions": contradictions,
    }
