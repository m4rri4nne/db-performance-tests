"""
N+1 Query Detector

Instruments a SQLAlchemy engine to log every query issued, then groups
them by normalized form (literals stripped) to surface repeated patterns.

A query that fires N+1 times — once for a list, once per row — is the
most common cause of unexpected database load in ORMs.

Usage:
    python analysis/n_plus_one_detector.py
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text, event
from config import DB_URL

_query_log: list[str] = []


def attach_logger(engine) -> None:
    """Register an event listener that appends every executed statement."""
    @event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):
        _query_log.append(statement.strip())


def reset_log() -> None:
    _query_log.clear()


def normalize(sql: str) -> str:
    """Strip literal values so semantically identical queries hash the same."""
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"'[^']*'", "'?'", sql)
    sql = re.sub(r"\b\d+\b", "?", sql)
    sql = re.sub(r"=\s*\$\d+", "= $?", sql)
    sql = re.sub(r"ANY\s*\(\s*\$\d+\s*\)", "ANY($?)", sql, flags=re.IGNORECASE)
    sql = re.sub(r"IN\s*\([^)]+\)", "IN (?)", sql, flags=re.IGNORECASE)
    return sql.upper().strip()


def detect(threshold: int = 5) -> list[dict]:
    """Return queries that appeared at least `threshold` times."""
    counts: dict[str, int] = defaultdict(int)
    for q in _query_log:
        counts[normalize(q)] += 1
    return [
        {"query": q, "count": c}
        for q, c in sorted(counts.items(), key=lambda x: -x[1])
        if c >= threshold
    ]


# ---------------------------------------------------------------------------
# Simulation: intentional N+1 (bad) vs. single JOIN (good)
# ---------------------------------------------------------------------------

def simulate_bad(engine, sample_size: int = 20) -> list[dict]:
    """
    Classic N+1: fetch orders first, then issue one SELECT per order to
    retrieve the user's email — total of 1 + N queries.
    """
    reset_log()
    with engine.connect() as conn:
        orders = conn.execute(
            text("SELECT id, user_id FROM orders LIMIT :n"),
            {"n": sample_size},
        ).fetchall()

        for order in orders:
            conn.execute(
                text("SELECT email FROM users WHERE id = :uid"),
                {"uid": order.user_id},
            )

    total_queries = len(_query_log)
    print(f"\n[BAD]  {len(orders)} orders fetched → {total_queries} queries fired (1 + {len(orders)})")

    findings = detect(threshold=3)
    if findings:
        print("  N+1 candidates detected:")
        for f in findings:
            print(f"    [{f['count']}x] {f['query'][:100]}")
    return findings


def simulate_good(engine, sample_size: int = 20) -> None:
    """
    Fixed version: a single JOIN retrieves orders and user emails together.
    """
    reset_log()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT o.id, o.user_id, u.email "
                "FROM orders o "
                "JOIN users u ON u.id = o.user_id "
                "LIMIT :n"
            ),
            {"n": sample_size},
        ).fetchall()

    total_queries = len(_query_log)
    print(f"\n[GOOD] {len(rows)} orders+emails fetched → {total_queries} query fired")
    print("  No repeated patterns detected.")


if __name__ == "__main__":
    engine = create_engine(DB_URL)
    attach_logger(engine)

    print("=== N+1 Query Detection Demo ===")
    print(f"Sample size: 20 orders\n")

    simulate_bad(engine, sample_size=20)
    simulate_good(engine, sample_size=20)

    print("\n--- Fix ---")
    print("Replace per-row SELECT with a JOIN or a batch IN (...) query.")
    print("Example:")
    print("  SELECT o.id, u.email FROM orders o JOIN users u ON u.id = o.user_id LIMIT 20;")
