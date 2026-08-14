"""
Dry-run test for src/mcp/client.py -- proves the initialize handshake,
tool-name discovery, result parsing, and placeholder substitution logic
against mocked HTTP responses. Does NOT prove the real server matches
these shapes -- that's what scripts/verify_mcp_connection.py is for, run
against a real bearer token, not something a mock can stand in for.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.mcp.client import MCPClient, MCPError


def _mock_response(json_body: dict, headers: dict = None):
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.raise_for_status.return_value = None
    mock.headers = headers or {"Content-Type": "application/json"}
    mock.text = json.dumps(json_body)
    mock.status_code = 200
    return mock


def _initialized_client() -> MCPClient:
    """Most tests care about behavior AFTER the handshake, not the
    handshake itself -- skip it directly rather than mocking two extra
    POSTs in every single test."""
    client = MCPClient("https://fake.example/mcp", "fake-token", "defaultdb")
    client._initialized = True
    return client


def test_initialize_handshake_captures_session_id_and_sets_accept_header():
    client = MCPClient("https://fake.example/mcp", "fake-token", "defaultdb")
    assert client._session.headers["Accept"] == "application/json, text/event-stream"

    init_response = _mock_response(
        {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
        headers={"Content-Type": "application/json", "Mcp-Session-Id": "abc123"},
    )
    notif_response = _mock_response({})

    with patch.object(client._session, "post", side_effect=[init_response, notif_response]) as mock_post:
        client._ensure_initialized()

    assert client._session.headers["Mcp-Session-Id"] == "abc123"
    assert client._initialized is True
    assert mock_post.call_count == 2  # initialize, then notifications/initialized
    print("OK: initialize handshake sends correct headers and captures the session ID")


def test_ensure_initialized_only_runs_once():
    client = _initialized_client()
    with patch.object(client._session, "post") as mock_post:
        client._ensure_initialized()
    mock_post.assert_not_called()
    print("OK: initialize is not re-run once already initialized")


def test_non_json_response_raises_diagnostic_error_not_bare_crash():
    """This is the actual bug that was hit: a non-JSON response used to
    crash with an opaque JSONDecodeError. Now it should raise a clear
    MCPError with the status/content-type/body snippet."""
    client = _initialized_client()

    html_response = MagicMock()
    html_response.raise_for_status.return_value = None
    html_response.headers = {"Content-Type": "text/html"}
    html_response.text = "<html><body>Not Found</body></html>"
    html_response.status_code = 200
    html_response.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")

    with patch.object(client._session, "post", return_value=html_response):
        try:
            client.list_tools()
            assert False, "should have raised MCPError"
        except MCPError as exc:
            assert "non-JSON" in str(exc)
            assert "text/html" in str(exc)

    print("OK: a non-JSON response now raises a diagnostic MCPError showing status/content-type/body, not a bare crash")


def test_sse_response_is_parsed_correctly():
    client = _initialized_client()

    sse_response = MagicMock()
    sse_response.raise_for_status.return_value = None
    sse_response.headers = {"Content-Type": "text/event-stream"}
    sse_response.text = (
        'event: message\n'
        'data: {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}\n\n'
    )
    sse_response.status_code = 200

    with patch.object(client._session, "post", return_value=sse_response):
        tools = client.list_tools()

    assert tools == []
    print("OK: an SSE-formatted response is parsed correctly, not treated as a parse failure")


def test_resolves_sql_tool_name_from_tools_list():
    client = _initialized_client()

    tools_list_response = _mock_response({
        "jsonrpc": "2.0", "id": 1,
        "result": {"tools": [
            {"name": "list_databases", "description": "..."},
            {"name": "select_query", "description": "Executes a SELECT statement"},
        ]},
    })

    with patch.object(client._session, "post", return_value=tools_list_response):
        name = client._resolve_sql_tool_name()

    assert name == "select_query"
    print("OK: SQL tool name resolved correctly from tools/list")


def test_resolution_fails_clearly_when_no_sql_tool_present():
    client = _initialized_client()

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
    client = _initialized_client()
    client._sql_tool_name = "select_query"  # skip discovery for this test

    tool_call_response = _mock_response({
        "jsonrpc": "2.0", "id": 2,
        "result": {"content": [{"type": "text", "text": json.dumps([{"test_value": 1}])}]},
    })

    with patch.object(client._session, "post", return_value=tool_call_response):
        rows = client.execute_sql("SELECT 1 AS test_value", [])

    assert rows == [{"test_value": 1}]
    print("OK: JSON-array-in-text-content result shape parses correctly")


def test_execute_sql_raises_clearly_on_unparseable_result():
    client = _initialized_client()
    client._sql_tool_name = "select_query"

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

    print("OK: an unparseable tool result fails loudly with a pointer to fix _parse_sql_result(), not silently")


def test_placeholder_substitution_escapes_and_types_correctly():
    from src.mcp.client import _substitute_placeholders

    rendered = _substitute_placeholders(
        "SELECT * FROM claims WHERE project = $1 AND embedding <-> $2 LIMIT $3",
        ["crynux", "[0.1,0.2]", 5],
    )
    assert "project = 'crynux'" in rendered
    assert "embedding <-> '[0.1,0.2]'" in rendered
    assert "LIMIT 5" in rendered  # integer, not quoted
    print("OK: placeholder substitution quotes strings and leaves integers bare")


def test_placeholder_substitution_escapes_embedded_quotes():
    from src.mcp.client import _substitute_placeholders

    rendered = _substitute_placeholders("SELECT * FROM x WHERE y = $1", ["O'Brien"])
    assert "y = 'O''Brien'" in rendered, "a single quote in a value must be doubled, not left to break the SQL"
    print("OK: embedded single quotes are escaped correctly, not left as an injection risk")


def test_execute_sql_sends_confirmed_real_argument_shape():
    """Locks in the argument shape confirmed against the real server:
    {"query": ..., "database": ..., "cluster_id": ...} -- not "sql", and
    database/cluster_id are real required arguments, not optional
    extras."""
    client = MCPClient("https://fake.example/mcp", "fake-token", "defaultdb", cluster_id="abc-123")
    client._initialized = True
    client._sql_tool_name = "select_query"

    tool_call_response = _mock_response({
        "jsonrpc": "2.0", "id": 2,
        "result": {"content": [{"type": "text", "text": json.dumps([{"test_value": 1}])}]},
    })

    with patch.object(client._session, "post", return_value=tool_call_response) as mock_post:
        client.execute_sql("SELECT 1 AS test_value", [])

    sent_payload = mock_post.call_args.kwargs["json"]
    arguments = sent_payload["params"]["arguments"]
    assert arguments["query"] == "SELECT 1 AS test_value"
    assert arguments["database"] == "defaultdb"
    assert arguments["cluster_id"] == "abc-123"
    assert "sql" not in arguments
    print("OK: sends the confirmed real argument shape (query/database/cluster_id), not the earlier wrong guess")


def test_execute_sql_omits_cluster_id_when_not_set():
    client = MCPClient("https://fake.example/mcp", "fake-token", "defaultdb")  # no cluster_id
    client._initialized = True
    client._sql_tool_name = "select_query"

    tool_call_response = _mock_response({
        "jsonrpc": "2.0", "id": 2,
        "result": {"content": [{"type": "text", "text": json.dumps([{"test_value": 1}])}]},
    })

    with patch.object(client._session, "post", return_value=tool_call_response) as mock_post:
        client.execute_sql("SELECT 1", [])

    arguments = mock_post.call_args.kwargs["json"]["params"]["arguments"]
    assert "cluster_id" not in arguments
    print("OK: cluster_id omitted entirely when not configured, not sent as an empty string")


if __name__ == "__main__":
    test_initialize_handshake_captures_session_id_and_sets_accept_header()
    test_ensure_initialized_only_runs_once()
    test_non_json_response_raises_diagnostic_error_not_bare_crash()
    test_sse_response_is_parsed_correctly()
    test_resolves_sql_tool_name_from_tools_list()
    test_resolution_fails_clearly_when_no_sql_tool_present()
    test_execute_sql_parses_json_array_result()
    test_execute_sql_raises_clearly_on_unparseable_result()
    test_placeholder_substitution_escapes_and_types_correctly()
    test_placeholder_substitution_escapes_embedded_quotes()
    test_execute_sql_sends_confirmed_real_argument_shape()
    test_execute_sql_omits_cluster_id_when_not_set()
    print("\nAll MCP client dry-run checks passed.")
