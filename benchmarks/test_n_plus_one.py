"""
N+1 Query Detection Tests

Verifies that the detector catches the classic N+1 pattern (one query per row)
and confirms that the JOIN-based fix produces no repeated patterns.

In CI this acts as a guard: if application queries are refactored to introduce
per-row SELECTs, the bad-pattern test will fail.

Run:
    pytest benchmarks/test_n_plus_one.py -v
"""

import pytest
from analysis.n_plus_one_detector import detect, simulate_bad, simulate_good


@pytest.mark.n_plus_one
def test_n_plus_one_detected_in_bad_pattern(instrumented_engine):
    findings = simulate_bad(instrumented_engine, sample_size=20)
    assert len(findings) > 0, (
        "N+1 pattern not detected. simulate_bad should produce repeated "
        "per-row SELECT queries that the detector flags."
    )


@pytest.mark.n_plus_one
def test_no_n_plus_one_in_optimized_query(instrumented_engine):
    simulate_good(instrumented_engine, sample_size=20)
    findings = detect(threshold=3)
    assert len(findings) == 0, (
        f"Unexpected repeated query patterns in JOIN-based query: {findings}. "
        "This suggests the optimized path is issuing per-row SELECTs."
    )
