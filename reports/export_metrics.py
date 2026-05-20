"""
Grafana Metrics Exporter

Writes benchmark results into a `benchmark_results` table in the same
PostgreSQL instance. Grafana reads from this table via its PostgreSQL
datasource to render latency trend panels.

Called automatically by query_regression_report.py after each run.
Can also be run standalone to backfill from saved JSON files:

    python reports/export_metrics.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text
from config import DB_URL

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS benchmark_results (
    id          SERIAL PRIMARY KEY,
    run_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    volume      TEXT        NOT NULL,
    query_label TEXT        NOT NULL,
    avg_ms      FLOAT       NOT NULL,
    p95_ms      FLOAT       NOT NULL,
    max_ms      FLOAT       NOT NULL
);
"""

_INSERT = """
INSERT INTO benchmark_results (run_at, volume, query_label, avg_ms, p95_ms, max_ms)
VALUES (:run_at, :volume, :query_label, :avg_ms, :p95_ms, :max_ms)
"""


def export(volume: str, results: list[dict], run_at: datetime | None = None) -> None:
    """Insert one benchmark run into benchmark_results."""
    ts = run_at or datetime.now(timezone.utc)
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text(_CREATE_TABLE))
        conn.execute(
            text(_INSERT),
            [
                {
                    "run_at": ts,
                    "volume": volume,
                    "query_label": r["query"],
                    "avg_ms": r["avg_ms"],
                    "p95_ms": r["p95_ms"],
                    "max_ms": r["max_ms"],
                }
                for r in results
            ],
        )
    print(f"  Exported {len(results)} rows to benchmark_results (volume={volume})")


def backfill_from_json() -> None:
    """Re-export all timestamped JSON files from reports/output/ to the table."""
    output_dir = Path(__file__).resolve().parents[1] / "reports" / "output"
    files = sorted(f for f in output_dir.glob("*_2*.json"))  # skip *_latest.json
    if not files:
        print("No timestamped result files found in reports/output/.")
        return

    for path in files:
        stem = path.stem                          # e.g. "low_20240501T120000Z"
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        volume, ts_str = parts
        try:
            run_at = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        results = json.loads(path.read_text())
        export(volume, results, run_at=run_at)
        print(f"  Backfilled {path.name}")


if __name__ == "__main__":
    print("Backfilling benchmark_results from saved JSON files...")
    backfill_from_json()
    print("Done. Open Grafana at http://localhost:3000 to see the data.")
