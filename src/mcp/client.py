"""
Minimal MCP (Model Context Protocol) HTTP client for the CockroachDB
Cloud Managed MCP Server. General JSON-RPC 2.0 / MCP client, not
CockroachDB-specific beyond the execute_sql() convenience wrapper.

Confirmed from CockroachDB Cloud docs (see infra/SETUP.md Step 5): the
server is an HTTPS endpoint, bearer-token authenticated, read-only by
default, exposing typed tools for SQL execution.

NOT yet confirmed against a live call -- this environment has no access
to your real MCP endpoint/token. execute_sql() discovers the SQL tool's
name dynamically via tools/list rather than hardcoding a guess, and
_parse_sql_result() defensively tries the most likely response shapes --
but run scripts/verify_mcp_connection.py once against your real bearer
token BEFORE trusting this in the demo, and adjust SQL_TOOL_NAME_HINTS /
_parse_sql_result() below if the real shapes differ from what's assumed.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import requests

log = logging.getLogger("agent_black_box.mcp")

# Matched against tools/list results by substring, case-insensitive, in
# priority order. Once verify_mcp_connection.py tells you the real name,
# either move it to the front of this list or just hardcode it directly
# in _resolve_sql_tool_name() below.
SQL_TOOL_NAME_HINTS = ["run_sql", "execute_sql", "sql_query", "query", "sql"]


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, endpoint: str, bearer_token: str, timeout_seconds: int = 20):
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        })
        self._request_id = 0
        self._sql_tool_name: Optional[str] = None

    def _call(self, method: str, params: Optional[dict] = None) -> dict:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}}
        response = self._session.post(self.endpoint, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise MCPError(f"MCP error calling {method}: {body['error']}")
        return body.get("result", {})

    def list_tools(self) -> list[dict]:
        result = self._call("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> Any:
        return self._call("tools/call", {"name": name, "arguments": arguments})

    def _resolve_sql_tool_name(self) -> str:
        if self._sql_tool_name:
            return self._sql_tool_name
        tools = self.list_tools()
        for hint in SQL_TOOL_NAME_HINTS:
            for tool in tools:
                if hint in tool.get("name", "").lower():
                    self._sql_tool_name = tool["name"]
                    log.info("mcp: resolved SQL tool name to %r", self._sql_tool_name)
                    return self._sql_tool_name
        raise MCPError(
            f"Could not find a SQL execution tool among: {[t.get('name') for t in tools]}. "
            f"Run scripts/verify_mcp_connection.py and hardcode the exact name in "
            f"SQL_TOOL_NAME_HINTS."
        )

    def execute_sql(self, sql: str, params: Optional[list] = None) -> list[dict]:
        """Runs a read-only SQL query through the MCP server, returns
        rows as a list of dicts. The server enforces read-only itself
        (infra/SETUP.md Step 5) -- this client doesn't second-guess that,
        it just calls the tool."""
        tool_name = self._resolve_sql_tool_name()
        raw_result = self.call_tool(tool_name, {"sql": sql, "params": params or []})
        return _parse_sql_result(raw_result)


def _parse_sql_result(raw_result: Any) -> list[dict]:
    """MCP tool results are typically {"content": [{"type": "text", "text": "..."}], ...}.
    UNCONFIRMED against the real server: whether that text is a JSON
    array of row objects, a JSON object with a 'rows' key, or something
    else. Tries the likely JSON shapes and raises clearly rather than
    silently returning garbage if the format doesn't match -- run
    verify_mcp_connection.py to see the real shape and fix this function
    if it differs."""
    content = raw_result.get("content") if isinstance(raw_result, dict) else None
    if not content:
        raise MCPError(f"Unexpected MCP tool result shape (no 'content'): {raw_result!r}")

    text_blocks = [block.get("text", "") for block in content if block.get("type") == "text"]
    if not text_blocks:
        raise MCPError(f"MCP tool result had no text content blocks: {raw_result!r}")

    combined = "\n".join(text_blocks)
    try:
        parsed = json.loads(combined)
    except json.JSONDecodeError as exc:
        raise MCPError(
            f"Could not parse MCP SQL tool result as JSON -- the real response shape "
            f"differs from what this client assumes. Raw text: {combined[:500]!r}"
        ) from exc

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and "rows" in parsed:
        return parsed["rows"]
    raise MCPError(f"Parsed MCP SQL result but didn't recognize its shape: {type(parsed)} -- {parsed!r}")
