"""
Deadlock Simulator

Demonstrates PostgreSQL's automatic deadlock detection using two concurrent
transactions that acquire row-level locks in opposite order.

Transaction A: locks order 1 → tries to lock order 2
Transaction B: locks order 2 → tries to lock order 1

PostgreSQL detects the cycle and rolls back one transaction (the "victim").

Usage:
    python analysis/deadlock_simulator.py
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text
from config import DB_URL


def _tx_a(engine, results: dict, barrier: threading.Barrier) -> None:
    """Acquires lock on order 1 first, then order 2."""
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE orders SET status = 'pending' WHERE id = 1"))
            barrier.wait()      # signal B to grab its first lock
            time.sleep(0.15)    # hold lock long enough for B to be waiting on order 1
            conn.execute(text("UPDATE orders SET status = 'paid' WHERE id = 2"))
            results["a"] = "committed"
    except Exception as exc:
        results["a"] = f"rolled back — {type(exc).__name__}"


def _tx_b(engine, results: dict, barrier: threading.Barrier) -> None:
    """Acquires lock on order 2 first, then order 1 — reverse of A."""
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE orders SET status = 'pending' WHERE id = 2"))
            barrier.wait()
            time.sleep(0.15)
            conn.execute(text("UPDATE orders SET status = 'paid' WHERE id = 1"))
            results["b"] = "committed"
    except Exception as exc:
        results["b"] = f"rolled back — {type(exc).__name__}"


def run_deadlock_scenario(engine) -> dict:
    results: dict = {}
    barrier = threading.Barrier(2)

    ta = threading.Thread(target=_tx_a, args=(engine, results, barrier))
    tb = threading.Thread(target=_tx_b, args=(engine, results, barrier))

    print("\n--- Scenario: classic deadlock (reverse lock acquisition order) ---")
    print("  Tx A: UPDATE order 1 → UPDATE order 2")
    print("  Tx B: UPDATE order 2 → UPDATE order 1")
    print("  Starting both transactions concurrently...\n")

    ta.start()
    time.sleep(0.02)    # stagger startup so A locks first
    tb.start()
    ta.join()
    tb.join()

    print(f"  Transaction A: {results.get('a', 'unknown')}")
    print(f"  Transaction B: {results.get('b', 'unknown')}")

    if "rolled back" in results.get("a", ""):
        victim = "A"
    elif "rolled back" in results.get("b", ""):
        victim = "B"
    else:
        victim = "none (no deadlock triggered — try again)"

    print(f"\n  PostgreSQL detected the cycle and rolled back Transaction {victim}.")
    print("  The surviving transaction committed. The rolled-back one can be retried.")
    return results


def print_mitigation() -> None:
    print("\n--- Prevention ---")
    print("  Always acquire locks in a consistent global order across all transactions.")
    print("  For rows: sort by primary key before updating.")
    print()
    print("  Bad  (can deadlock):")
    print("    Tx A: UPDATE orders WHERE id = 1; UPDATE orders WHERE id = 2;")
    print("    Tx B: UPDATE orders WHERE id = 2; UPDATE orders WHERE id = 1;")
    print()
    print("  Good (deadlock-safe):")
    print("    Both transactions process ids in ascending order:")
    print("    UPDATE orders SET ... WHERE id IN (1, 2) ORDER BY id;")
    print("    -- or sort ids in application code before issuing UPDATEs")


if __name__ == "__main__":
    print("=== Deadlock Simulator ===")
    engine = create_engine(DB_URL, pool_size=5)
    run_deadlock_scenario(engine)
    print_mitigation()
