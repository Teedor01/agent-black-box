from __future__ import annotations

import certifi
import psycopg
from contextlib import contextmanager

from src.agent.config import Config


@contextmanager
def get_connection(config: Config):
    
    conn = psycopg.connect(config.cockroachdb_connection_string, sslrootcert=certifi.where())
    try:
        yield conn
    finally:
        conn.close()


def run_in_transaction(config: Config, fn, *args, max_retries: int = 3, **kwargs):
   
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
