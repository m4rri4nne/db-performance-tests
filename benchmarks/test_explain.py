"""
EXPLAIN ANALYZE Plan Regression Tests

Captures PostgreSQL execution plans and asserts structural and timing constraints:
- The planner must not use a Seq Scan on queries that have a supporting index.
- Actual execution time must stay within the slow-query threshold.

In CI these tests act as a migration safety net: adding an index should make
them pass; dropping one (or a migration that removes it) will make them fail.

Run:
    pytest benchmarks/test_explain.py -v
"""

import pytest
from analysis.explain_analyzer import capture_plan
from config import SLOW_QUERY_THRESHOLD_MS

_ORDER_HISTORY_SQL = (
    "SELECT id, status, total FROM orders "
    "WHERE user_id = :uid ORDER BY created_at DESC LIMIT 20"
)
_ORDER_HISTORY_PARAMS = {"uid": 1}

_USER_LOOKUP_SQL = (
    "SELECT id, email, country FROM users WHERE email = (SELECT email FROM users LIMIT 1)"
)


@pytest.mark.explain
def test_order_history_no_seq_scan(engine):
    plan = capture_plan(engine, _ORDER_HISTORY_SQL, _ORDER_HISTORY_PARAMS)
    node_type = plan["Plan"]["Node Type"]
    assert node_type != "Seq Scan", (
        f"order_history is using a Seq Scan (cost={plan['Plan']['Total Cost']:.1f}). "
        "Add an index on orders(user_id, created_at DESC) to fix this."
    )


@pytest.mark.explain
def test_order_history_within_threshold(engine):
    plan = capture_plan(engine, _ORDER_HISTORY_SQL, _ORDER_HISTORY_PARAMS)
    actual_ms = plan["Plan"]["Actual Total Time"]
    assert actual_ms < SLOW_QUERY_THRESHOLD_MS, (
        f"order_history actual time {actual_ms:.1f} ms exceeds "
        f"threshold {SLOW_QUERY_THRESHOLD_MS} ms. "
        "Run 'python analysis/explain_analyzer.py' to inspect the full plan."
    )


@pytest.mark.explain
def test_user_lookup_no_seq_scan(engine):
    plan = capture_plan(engine, _USER_LOOKUP_SQL)
    node_type = plan["Plan"]["Node Type"]
    assert node_type != "Seq Scan", (
        f"user_lookup is using a Seq Scan (cost={plan['Plan']['Total Cost']:.1f}). "
        "Add an index on users(email) to fix this."
    )


@pytest.mark.explain
def test_user_lookup_within_threshold(engine):
    plan = capture_plan(engine, _USER_LOOKUP_SQL)
    actual_ms = plan["Plan"]["Actual Total Time"]
    assert actual_ms < SLOW_QUERY_THRESHOLD_MS, (
        f"user_lookup actual time {actual_ms:.1f} ms exceeds "
        f"threshold {SLOW_QUERY_THRESHOLD_MS} ms."
    )
