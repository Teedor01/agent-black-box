from __future__ import annotations

import json
import logging
from typing import Any, Optional

import requests

log = logging.getLogger("agent_black_box.mcp")

SQL_TOOL_NAME_HINTS = ["select_query", "run_sql", "execute_sql", "sql_query", "query", "sql"]

MCP_PROTOCOL_VERSION = "2025-03-26"


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, endpoint: str, bearer_token: str, database: str,
                 cluster_id: str = "", timeout_seconds: int = 20):
        self.endpoint = endpoint
        self.database = database
        self.cluster_id = cluster_id
        self.timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })
        self._request_id = 0
        self._sql_tool_name: Optional[str] = None
        self._initialized = False

    def _raw_post(self, payload: dict) -> requests.Response:
        response = self._session.post(self.endpoint, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response

    def _parse_response_body(self, response: requests.Response) -> dict:
      
        content_type = response.headers.get("Content-Type", "")

        if "text/event-stream" in content_type:
            data_lines = [
                line[len("data:"):].strip()
                for line in response.text.splitlines()
                if line.startswith("data:")
            ]
            if not data_lines:
                raise MCPError(
                    f"Got an SSE response with no 'data:' lines. Status={response.status_code}, "
                    f"raw body: {response.text[:500]!r}"
                )
            try:
                return json.loads(data_lines[-1])
            except json.JSONDecodeError as exc:
                raise MCPError(
                    f"Could not parse the SSE 'data:' payload as JSON: {data_lines[-1][:500]!r}"
                ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise MCPError(
                f"MCP server returned a non-JSON, non-SSE response. "
                f"Status={response.status_code}, Content-Type={content_type!r}, "
                f"raw body (first 500 chars): {response.text[:500]!r}. "
                f"This usually means auth failed silently, the endpoint URL is wrong, "
                f"or the mcp-cluster-id header (if you're using one) doesn't match a "
                f"cluster this credential can access."
            ) from exc

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        self._request_id += 1
        init_payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "agent-black-box", "version": "0.1"},
            },
        }
        response = self._raw_post(init_payload)
        body = self._parse_response_body(response)
        if "error" in body:
            raise MCPError(f"MCP initialize failed: {body['error']}")

        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self._session.headers["Mcp-Session-Id"] = session_id
            log.info("mcp: session established (Mcp-Session-Id present)")
        else:
            log.info("mcp: initialized with no Mcp-Session-Id header returned (server may not require one)")

      
        self._session.post(
            self.endpoint,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            timeout=self.timeout_seconds,
        )

        self._initialized = True

    def _call(self, method: str, params: Optional[dict] = None) -> dict:
        self._ensure_initialized()

        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}}
        response = self._raw_post(payload)
        body = self._parse_response_body(response)
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

    def execute_sql(self, sql_template: str, params: Optional[list] = None) -> list[dict]:
      
        tool_name = self._resolve_sql_tool_name()
        rendered_sql = _substitute_placeholders(sql_template, params or [])
        arguments = {"query": rendered_sql, "database": self.database}
        if self.cluster_id:
            arguments["cluster_id"] = self.cluster_id
        raw_result = self.call_tool(tool_name, arguments)
        return _parse_sql_result(raw_result)


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _substitute_placeholders(sql_template: str, params: list) -> str:
    rendered = sql_template
    for i, value in enumerate(params, start=1):
        rendered = rendered.replace(f"${i}", _sql_literal(value))
    return rendered


def _parse_sql_result(raw_result: Any) -> list[dict]:
   
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
