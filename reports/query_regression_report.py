"""
Query Regression Report

Runs the benchmark suite, compares results against the last saved run,
and prints a delta table showing which queries got faster or slower.

Designed to be run before and after a schema migration so you can measure
the performance impact of every change.

Workflow:
    1. python reports/query_regression_report.py          # baseline (before migration)
    2. Apply migration (e.g. python scripts/setup_schema.py --schema v2_add_indexes/002_add_indexes)
    3. python reports/query_regression_report.py          # after — delta shows the impact

Usage:
    python reports/query_regression_report.py [low|medium|high]
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tabulate import tabulate
from benchmarks.scenarios.run_benchmark import run_all, VOLUMES
from reports.export_metrics import export as export_to_grafana

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "reports" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _latest_path(volume: str) -> Path:
    return OUTPUT_DIR / f"{volume}_latest.json"


def _timestamped_path(volume: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return OUTPUT_DIR / f"{volume}_{ts}.json"


def load_previous(volume: str) -> list[dict] | None:
    path = _latest_path(volume)
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_results(volume: str, results: list[dict]) -> None:
    data = json.dumps(results, indent=2)
    _timestamped_path(volume).write_text(data)
    _latest_path(volume).write_text(data)


def build_table(current: list[dict], previous: list[dict] | None) -> list[list]:
    prev_map = {r["query"]: r for r in (previous or [])}
    rows = []
    for r in current:
        prev = prev_map.get(r["query"])
        if prev:
            diff = r["avg_ms"] - prev["avg_ms"]
            pct = (diff / prev["avg_ms"]) * 100 if prev["avg_ms"] else 0
            delta = f"{'+' if diff >= 0 else ''}{pct:.1f}%"
            flag = " ⚠" if pct > 20 else (" ✓" if pct < -10 else "")
        else:
            delta, flag = "—", ""
        rows.append([r["query"], r["avg_ms"], r["p95_ms"], r["max_ms"], f"{delta}{flag}"])
    return rows


def run(volumes: list[str] | None = None) -> None:
    targets = volumes or list(VOLUMES.keys())
    for volume in targets:
        current = run_all(volume)
        previous = load_previous(volume)
        save_results(volume, current)
        try:
            export_to_grafana(volume, current)
        except Exception as exc:
            print(f"  [Grafana export skipped: {exc}]")

        print(f"\n{'='*60}")
        print(f"Regression Report — volume: {volume}")
        if previous:
            print("Comparing against last saved run.")
        else:
            print("No previous run found — this result will be the baseline.")
        print(f"{'='*60}")

        rows = build_table(current, previous)
        print(tabulate(
            rows,
            headers=["Query", "avg ms", "p95 ms", "max ms", "Δ vs last"],
            tablefmt="simple",
        ))

    print(f"\nResults saved to {OUTPUT_DIR.relative_to(Path.cwd())}/")
    print("Re-run after a migration to measure the impact.")


if __name__ == "__main__":
    requested = sys.argv[1:] if len(sys.argv) > 1 else None
    if requested and not all(v in VOLUMES for v in requested):
        valid = ", ".join(VOLUMES)
        print(f"Unknown volume. Valid options: {valid}")
        sys.exit(1)
    run(requested)
