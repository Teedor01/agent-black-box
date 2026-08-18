"""
Applies src/db/seed_sources.sql -- the real, curated demo corpus sources
from Day 2. Run once, after apply_schema.py, before the first real
episode.

Usage (cmd.exe): python scripts\\seed_sources.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()


def main():
    conn_string = os.environ.get("COCKROACHDB_CONNECTION_STRING")
    if not conn_string:
        print("ERROR: COCKROACHDB_CONNECTION_STRING not set (check your .env file).", file=sys.stderr)
        sys.exit(1)

    seed_path = Path(__file__).resolve().parent.parent / "src" / "db" / "seed_sources.sql"
    sql = seed_path.read_text()

    print(f"Applying {seed_path} ...")
    with psycopg.connect(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    with psycopg.connect(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT project, domain, url FROM sources ORDER BY project, domain;")
            rows = cur.fetchall()

    print(f"\n{len(rows)} sources now in the table:")
    for project, domain, url in rows:
        print(f"  [{project}] {domain} -- {url}")


if __name__ == "__main__":
    main()
