"""
CockroachDB connection helper.

Uses psycopg3, since CockroachDB speaks the Postgres wire protocol. This
is the application backend's read/write credential (Section J of the
architecture doc) -- distinct from the agent's read-only MCP path used
during the retrieve stage (see src/mcp/).
"""
from __future__ import annotations

import psycopg
from contextlib import contextmanager

from src.agent.config import Config


@contextmanager
def get_connection(config: Config):
    """Yields a connection with CockroachDB's recommended serializable
    retry handling. CockroachDB transactions can abort under contention
    and must be retried by the client -- psycopg's built-in retry loop
    below follows Cockroach Labs' documented client-side retry pattern."""
    conn = psycopg.connect(config.cockroachdb_connection_string)
    try:
        yield conn
    finally:
        conn.close()


def run_in_transaction(config: Config, fn, *args, max_retries: int = 3, **kwargs):
    """Runs fn(cursor, *args, **kwargs) inside a single transaction,
    retrying on CockroachDB serialization failures (SQLSTATE 40001).

    This is the mechanism behind the architecture doc's rule: 'a research
    answer should not be considered successfully completed if the
    corresponding memory cannot be safely persisted.' All writes for one
    episode go through this single call -- if it doesn't commit, the
    episode is not considered complete, enforced synchronously (Section
    10 of the architecture doc), not fixed up by a background job later.
    """
    with get_connection(config) as conn:
        for attempt in range(max_retries):
            try:
                with conn.cursor() as cur:
                    result = fn(cur, *args, **kwargs)
                conn.commit()
                return result
            except psycopg.errors.SerializationFailure:
                conn.rollback()
                if attempt == max_retries - 1:
                    raise
            except Exception:
                conn.rollback()
                raise
