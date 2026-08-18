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
            tables = [row[1] for row in cur.fetchall()]  
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
