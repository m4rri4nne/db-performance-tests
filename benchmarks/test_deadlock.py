"""
Deadlock Detection Tests

Verifies that PostgreSQL's automatic deadlock detection works as expected:
given two transactions acquiring locks in reverse order, exactly one should
be rolled back and one should commit.

In CI this confirms the database is correctly configured and that deadlock
detection is active (not disabled via lock_timeout or other settings).

Run:
    pytest benchmarks/test_deadlock.py -v
"""

import pytest
from analysis.deadlock_simulator import run_deadlock_scenario


@pytest.mark.deadlock
def test_deadlock_rolls_back_one_transaction(engine):
    results = run_deadlock_scenario(engine)

    assert any("committed" in str(v) for v in results.values()), (
        "No transaction committed. Both may have failed or timed out."
    )
    assert any("rolled back" in str(v) for v in results.values()), (
        "No transaction was rolled back. PostgreSQL deadlock detection may not "
        "have triggered — check lock_timeout and deadlock_timeout settings."
    )


@pytest.mark.deadlock
def test_deadlock_only_one_victim(engine):
    results = run_deadlock_scenario(engine)

    rolled_back = [v for v in results.values() if "rolled back" in str(v)]
    assert len(rolled_back) == 1, (
        f"Expected exactly 1 victim, got {len(rolled_back)}: {results}"
    )
