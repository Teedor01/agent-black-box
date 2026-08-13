"""
Run this once against your real MCP bearer token to confirm what
src/mcp/client.py assumes: the tool name for SQL execution, and the
shape of a tool result. Do this BEFORE relying on memory.py's MCP-based
retrieval in the demo -- if anything below fails or looks unexpected,
fix src/mcp/client.py's SQL_TOOL_NAME_HINTS or _parse_sql_result()
accordingly, not memory.py.

Usage (cmd.exe): python scripts\\verify_mcp_connection.py
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

from src.mcp.client import MCPClient

load_dotenv()


def main():
    endpoint = os.environ["COCKROACHDB_MCP_ENDPOINT"]
    token = os.environ["COCKROACHDB_MCP_BEARER_TOKEN"]

    client = MCPClient(endpoint, token)

    print(f"Connecting to {endpoint} ...")
    tools = client.list_tools()
    print(f"\n{len(tools)} tools available:")
    for tool in tools:
        print(f"  - {tool.get('name')}: {tool.get('description', '')[:100]}")

    print("\nResolving SQL tool name via SQL_TOOL_NAME_HINTS ...")
    tool_name = client._resolve_sql_tool_name()
    print(f"Resolved to: {tool_name!r}")

    print("\nCalling it directly with a trivial query (SELECT 1) to see the RAW shape ...")
    raw = client.call_tool(tool_name, {"sql": "SELECT 1 AS test_value", "params": []})
    print(json.dumps(raw, indent=2)[:2000])

    print("\nNow through execute_sql() -- the parsed path memory.py actually uses ...")
    try:
        rows = client.execute_sql("SELECT 1 AS test_value", [])
        print(f"Parsed rows: {rows}")
        if rows and rows[0].get("test_value") == 1:
            print("\nOK -- execute_sql() is working correctly against the real server.")
        else:
            print("\nParsed without error, but the value looks wrong -- inspect the raw shape above.")
    except Exception as exc:
        print(f"\nFAILED to parse: {exc}")
        print("Fix src/mcp/client.py's _parse_sql_result() to match the raw shape printed above, then re-run this script.")


if __name__ == "__main__":
    main()
