"""
Dry-run test for src/mcp/client.py -- proves tool-name discovery and
result parsing logic against mocked HTTP responses shaped like what the
MCP spec and CockroachDB's docs describe. Does NOT prove the real server
matches these shapes -- that's what scripts/verify_mcp_connection.py is
for, run against a real bearer token, not something a mock can stand in
for.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.mcp.client import MCPClient, MCPError


def _mock_response(json_body: dict):
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.raise_for_status.return_value = None
    return mock


def test_resolves_sql_tool_name_from_tools_list():
    client = MCPClient("https://fake.example/mcp", "fake-token")

    tools_list_response = _mock_response({
        "jsonrpc": "2.0", "id": 1,
        "result": {"tools": [
            {"name": "list_databases", "description": "..."},
            {"name": "run_sql", "description": "Executes a SQL query"},
        ]},
    })

    with patch.object(client._session, "post", return_value=tools_list_response):
        name = client._resolve_sql_tool_name()

    assert name == "run_sql"
    print("OK: SQL tool name resolved correctly from tools/list")


def test_resolution_fails_clearly_when_no_sql_tool_present():
    client = MCPClient("https://fake.example/mcp", "fake-token")

    tools_list_response = _mock_response({
        "jsonrpc": "2.0", "id": 1,
        "result": {"tools": [{"name": "list_databases", "description": "..."}]},
    })

    with patch.object(client._session, "post", return_value=tools_list_response):
        try:
            client._resolve_sql_tool_name()
            assert False, "should have raised MCPError"
        except MCPError as exc:
            assert "Could not find a SQL execution tool" in str(exc)

    print("OK: missing SQL tool raises a clear, actionable error instead of silently failing")


def test_execute_sql_parses_json_array_result():
    client = MCPClient("https://fake.example/mcp", "fake-token")
    client._sql_tool_name = "run_sql"  # skip discovery for this test

    tool_call_response = _mock_response({
        "jsonrpc": "2.0", "id": 2,
        "result": {"content": [{"type": "text", "text": json.dumps([{"test_value": 1}])}]},
    })

    with patch.object(client._session, "post", return_value=tool_call_response):
        rows = client.execute_sql("SELECT 1 AS test_value", [])

    assert rows == [{"test_value": 1}]
    print("OK: JSON-array-in-text-content result shape parses correctly")


def test_execute_sql_raises_clearly_on_unparseable_result():
    client = MCPClient("https://fake.example/mcp", "fake-token")
    client._sql_tool_name = "run_sql"

    tool_call_response = _mock_response({
        "jsonrpc": "2.0", "id": 2,
        "result": {"content": [{"type": "text", "text": "not json at all"}]},
    })

    with patch.object(client._session, "post", return_value=tool_call_response):
        try:
            client.execute_sql("SELECT 1", [])
            assert False, "should have raised MCPError"
        except MCPError as exc:
            assert "Could not parse" in str(exc)

    print("OK: an unparseable result shape fails loudly with a pointer to fix _parse_sql_result(), not silently")


if __name__ == "__main__":
    test_resolves_sql_tool_name_from_tools_list()
    test_resolution_fails_clearly_when_no_sql_tool_present()
    test_execute_sql_parses_json_array_result()
    test_execute_sql_raises_clearly_on_unparseable_result()
    print("\nAll MCP client dry-run checks passed.")
