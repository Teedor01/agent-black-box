from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.mcp.client import MCPClient, MCPError

load_dotenv()


def main():
    endpoint = os.environ["COCKROACHDB_MCP_ENDPOINT"]
    token = os.environ["COCKROACHDB_MCP_BEARER_TOKEN"]
    database = os.environ["COCKROACHDB_MCP_DATABASE"]
    cluster_id = os.environ.get("COCKROACHDB_MCP_CLUSTER_ID", "")

    client = MCPClient(endpoint, token, database, cluster_id)
    if cluster_id:
        print(f"Using cluster_id: {cluster_id}")

    print(f"Connecting to {endpoint} (database={database!r}) ...")
    try:
        tools = client.list_tools()
    except MCPError as exc:
        print(f"\nFAILED to connect or authenticate: {exc}")
        print(
            "\nMost likely causes, in order of likelihood:\n"
            "  1. COCKROACHDB_MCP_BEARER_TOKEN is a dev-time OAuth token, not a Service Account "
            "API key, Lambda (and this script) needs the API key from infra/SETUP.md Step 5b.\n"
            "  2. The API key was copied incorrectly, has extra whitespace, or has expired.\n"
            "  3. The cluster needs mcp-cluster-id scoping, set COCKROACHDB_MCP_CLUSTER_ID in .env.\n"
            "  4. COCKROACHDB_MCP_ENDPOINT is wrong, should be https://cockroachlabs.cloud/mcp."
        )
        sys.exit(1)

    print(f"\n{len(tools)} tools available:")
    for tool in tools:
        print(f"  - {tool.get('name')}: {tool.get('description', '')[:100]}")
        schema = tool.get("inputSchema")
        if schema:
            print(f"      inputSchema: {json.dumps(schema)}")

    print("\nResolving SQL tool name (expecting 'select_query') ...")
    tool_name = client._resolve_sql_tool_name()
    print(f"Resolved to: {tool_name!r}")
    if tool_name != "select_query":
        print(
            "NOTE: this differs from the confirmed real tool name (select_query), "
            "check the inputSchema printed above for the tool actually matched."
        )

    print("\nSanity check: does list_databases work? (narrows whether 'unauthorized' is specific to select_query or blanket) ...")
    try:
        list_dbs_result = client.call_tool("list_databases", {"cluster_id": cluster_id} if cluster_id else {})
        print("list_databases succeeded:")
        print(json.dumps(list_dbs_result, indent=2)[:1000])
    except MCPError as exc:
        print(f"list_databases ALSO failed: {exc}")
        print("This means the role/permission problem is blanket, not select_query-specific, check the service account's role assignment on this exact cluster in the Cloud Console.")

    print("\nCalling select_query directly with a trivial query (SELECT 1) to see the RAW shape ...")
    arguments = {"query": "SELECT 1 AS test_value", "database": database}
    if cluster_id:
        arguments["cluster_id"] = cluster_id
    raw = client.call_tool(tool_name, arguments)
    print(json.dumps(raw, indent=2)[:2000])

    print("\nNow through execute_sql(); the parsed path memory.py actually uses ...")
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
