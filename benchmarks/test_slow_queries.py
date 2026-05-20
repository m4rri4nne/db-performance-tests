"""
Slow Query Threshold Tests

Asserts that critical queries complete within the acceptable latency budget
defined in config.SLOW_QUERY_THRESHOLD_MS.

These tests act as a regression gate: a schema change or missing index that
causes a query to cross the threshold will fail the suite.

Run:
    pytest benchmarks/test_slow_queries.py -v
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text
from config import DB_URL, SLOW_QUERY_THRESHOLD_MS

engine = create_engine(DB_URL)

# ---------------------------------------------------------------------------
# Queries under test — each tuple is (label, sql)
# ---------------------------------------------------------------------------

CRITICAL_QUERIES = [
    (
        "user_lookup",
        "SELECT id, email, country FROM users WHERE email = (SELECT email FROM users LIMIT 1)",
    ),
    (
        "order_history",
        "SELECT id, status, total FROM orders WHERE user_id = 1 ORDER BY created_at DESC LIMIT 20",
    ),
    (
        "inventory_search",
        "SELECT product_id, name, stock FROM inventory WHERE category = 'electronics' AND stock > 0 LIMIT 50",
    ),
    (
        "order_with_items",
        (
            "SELECT o.id, o.status, oi.product_id, oi.quantity "
            "FROM orders o "
            "JOIN order_items oi ON oi.order_id = o.id "
            "WHERE o.user_id = 1"
        ),
    ),
    (
        "revenue_by_country",
        (
            "SELECT u.country, SUM(o.total) AS revenue "
            "FROM orders o "
            "JOIN users u ON u.id = o.user_id "
            "WHERE o.status = 'paid' "
            "GROUP BY u.country "
            "ORDER BY revenue DESC"
        ),
    ),
]


@pytest.mark.parametrize("label,sql", CRITICAL_QUERIES)
def test_query_within_threshold(label: str, sql: str):
    with engine.connect() as conn:
        start = time.perf_counter()
        conn.execute(text(sql))
        elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < SLOW_QUERY_THRESHOLD_MS, (
        f"[{label}] took {elapsed_ms:.1f} ms — "
        f"exceeds threshold of {SLOW_QUERY_THRESHOLD_MS} ms. "
        f"Run 'python analysis/explain_analyzer.py' to inspect the plan."
    )
