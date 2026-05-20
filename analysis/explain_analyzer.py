"""
EXPLAIN ANALYZE Plan Comparator

Captures PostgreSQL execution plans (EXPLAIN ANALYZE BUFFERS) before and
after a schema change (e.g. adding an index or migration) and saves them
as JSON for diff comparison.

This is the engine behind query regression tracking: run it before
applying a migration, apply it, run again, then compare.

Usage:
    python analysis/explain_analyzer.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text
from config import DB_URL

PLANS_DIR = Path(__file__).resolve().parents[1] / "reports" / "plans"
PLANS_DIR.mkdir(parents=True, exist_ok=True)


def capture_plan(engine, sql: str, params: dict | None = None) -> dict:
    """Run EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) and return the parsed plan."""
    with engine.connect() as conn:
        row = conn.execute(
            text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"),
            params or {},
        )
        return row.fetchone()[0][0]


def save_plan(plan: dict, label: str) -> Path:
    safe = label.replace(" ", "_").replace("/", "-")
    path = PLANS_DIR / f"{safe}.json"
    path.write_text(json.dumps(plan, indent=2))
    return path


def load_plan(label: str) -> dict:
    safe = label.replace(" ", "_").replace("/", "-")
    path = PLANS_DIR / f"{safe}.json"
    if not path.exists():
        raise FileNotFoundError(f"No saved plan for label '{label}' at {path}")
    return json.loads(path.read_text())


def summarize(plan: dict, indent: int = 2) -> None:
    pad = " " * indent
    node = plan["Plan"]
    print(f"{pad}Node type:   {node['Node Type']}")
    print(f"{pad}Total cost:  {node['Total Cost']:.2f}")
    print(f"{pad}Actual rows: {node['Actual Rows']}")
    print(f"{pad}Actual ms:   {node['Actual Total Time']:.3f}")
    if "Plans" in node:
        for child in node["Plans"]:
            print(f"{pad}  └─ {child['Node Type']} (rows={child['Actual Rows']})")


def compare(engine, label_before: str, label_after: str, sql: str, params: dict | None = None) -> None:
    """
    Captures two plans in sequence. Place the schema change (CREATE INDEX,
    ALTER TABLE, etc.) between calling this function and the second capture —
    or use capture_before / capture_after directly.
    """
    print(f"\n=== Before: {label_before} ===")
    before = capture_plan(engine, sql, params)
    summarize(before)
    path = save_plan(before, label_before)
    print(f"  Saved → {path.relative_to(Path.cwd())}")

    print(f"\n=== After:  {label_after} ===")
    after = capture_plan(engine, sql, params)
    summarize(after)
    path = save_plan(after, label_after)
    print(f"  Saved → {path.relative_to(Path.cwd())}")

    delta = after["Plan"]["Actual Total Time"] - before["Plan"]["Actual Total Time"]
    direction = "faster" if delta < 0 else "slower"
    print(f"\n  Δ actual time: {delta:+.3f} ms  ({direction})")


def diff_saved(label_before: str, label_after: str) -> None:
    """Load two previously saved plans and print the diff summary."""
    before = load_plan(label_before)
    after = load_plan(label_after)

    print(f"\n=== Plan diff: '{label_before}'  →  '{label_after}' ===")
    print("\nBefore:")
    summarize(before)
    print("\nAfter:")
    summarize(after)

    b_time = before["Plan"]["Actual Total Time"]
    a_time = after["Plan"]["Actual Total Time"]
    b_cost = before["Plan"]["Total Cost"]
    a_cost = after["Plan"]["Total Cost"]

    print(f"\n  Δ actual time:  {a_time - b_time:+.3f} ms")
    print(f"  Δ planner cost: {a_cost - b_cost:+.2f}")


# ---------------------------------------------------------------------------
# Demo: order_history before/after adding a covering index
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    engine = create_engine(DB_URL)

    SQL = (
        "SELECT id, status, total FROM orders "
        "WHERE user_id = :uid ORDER BY created_at DESC LIMIT 20"
    )
    PARAMS = {"uid": 1}

    print("=== Explain Analyzer — order_history demo ===")

    # Ensure we start clean
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS idx_orders_user_created"))

    print("\n[Step 1] Capture plan WITHOUT index")
    before = capture_plan(engine, SQL, PARAMS)
    summarize(before)
    save_plan(before, "order_history_before_index")

    print("\n[Step 2] Create index")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX idx_orders_user_created ON orders(user_id, created_at DESC)"
        ))
    print("  idx_orders_user_created created.")

    print("\n[Step 3] Capture plan WITH index")
    after = capture_plan(engine, SQL, PARAMS)
    summarize(after)
    save_plan(after, "order_history_after_index")

    delta = after["Plan"]["Actual Total Time"] - before["Plan"]["Actual Total Time"]
    print(f"\nΔ actual time: {delta:+.3f} ms  ({'faster' if delta < 0 else 'slower'})")
    print("\nPlans saved to reports/plans/. Re-run diff_saved() to compare at any time.")
