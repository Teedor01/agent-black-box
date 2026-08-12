"""
Applies src/db/schema.sql to CockroachDB directly via psycopg -- no
cockroach CLI binary required. Useful on Windows where getting the CLI
onto PATH is its own fight not worth having.

Usage (cmd.exe):
    set COCKROACHDB_CONNECTION_STRING=postgresql://...
    python scripts\\apply_schema.py

Or, since you already have a .env file for the agent loop, this reads
from COCKROACHDB_CONNECTION_STRING via python-dotenv automatically if a
.env file is present in the working directory -- no need to set it twice.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
import os

load_dotenv()


def main():
    conn_string = os.environ.get("COCKROACHDB_CONNECTION_STRING")
    if not conn_string:
        print("ERROR: COCKROACHDB_CONNECTION_STRING not set (check your .env file).", file=sys.stderr)
        sys.exit(1)

    schema_path = Path(__file__).resolve().parent.parent / "src" / "db" / "schema.sql"
    sql = schema_path.read_text()

    print(f"Applying {schema_path} ...")
    with psycopg.connect(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("Schema applied successfully.")

    print("\nVerifying tables ...")
    with psycopg.connect(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES;")
            tables = [row[1] for row in cur.fetchall()]  # (schema, table_name, ...)
    expected = {"sources", "episodes", "episode_sources", "claims", "lessons", "contradictions"}
    found = set(tables)
    print(f"Found tables: {sorted(found)}")
    missing = expected - found
    if missing:
        print(f"WARNING: missing expected tables: {missing}", file=sys.stderr)
        sys.exit(1)
    print("All six expected tables present.")


if __name__ == "__main__":
    main()
