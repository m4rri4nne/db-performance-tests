# Database Performance Testing Suite — Implementation Guide

**Focus scenarios:** N+1 Query Detection · Deadlock Simulation · Query Regression Tracking Across Schema Changes

---

## Project structure

```
db-performance-tests/
├── analysis/
│   ├── n_plus_one_detector.py      # N+1 detection & simulation
│   ├── deadlock_simulator.py       # Deadlock demo & mitigation guide
│   └── explain_analyzer.py         # EXPLAIN ANALYZE plan capture & diff
├── benchmarks/
│   ├── queries/                    # SQL files for individual queries
│   ├── scenarios/
│   │   └── run_benchmark.py        # Volume benchmark runner
│   └── test_slow_queries.py        # pytest latency threshold gate
├── data/
│   ├── distributions.json
│   └── seed.py                     # Deterministic data generator
├── docker/
│   └── docker-compose.yml
├── migrations/
│   ├── baseline/
│   │   └── 001_initial_schema.sql
│   └── v2_add_indexes/
│       └── 002_add_indexes.sql     # Sample migration for regression demo
├── reports/
│   ├── output/                     # Timestamped benchmark JSON results
│   ├── plans/                      # Saved EXPLAIN plans (JSON)
│   └── query_regression_report.py  # Regression delta reporter
├── scripts/
│   └── setup_schema.py
└── config.py
```

---

## Phase 1 — Environment Setup

### Step 1: Initialize the project

```bash
git init
touch .gitignore
```

Add to `.gitignore`:
```
__pycache__/
*.pyc
.env
reports/output/
reports/plans/
data/generated/
```

---

### Step 2: Dockerized PostgreSQL

`docker/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: perftest
      POSTGRES_PASSWORD: perftest
      POSTGRES_DB: perfdb
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./docker/init.sql:/docker-entrypoint-initdb.d/init.sql
    command: >
      postgres
        -c shared_preload_libraries=pg_stat_statements
        -c pg_stat_statements.track=all
        -c log_min_duration_statement=100
        -c log_destination=csvlog
        -c logging_collector=on

volumes:
  pgdata:
```

`docker/init.sql`:
```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

```bash
docker compose -f docker/docker-compose.yml up -d
```

---

### Step 3: Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install psycopg2-binary sqlalchemy faker pytest python-dotenv tabulate
pip freeze > requirements.txt
```

`.env`:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=perfdb
DB_USER=perftest
DB_PASSWORD=perftest
```

`config.py`:
```python
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)
SLOW_QUERY_THRESHOLD_MS = 200
```

---

## Phase 2 — Schema & Data

### Step 4: Baseline schema

`migrations/baseline/001_initial_schema.sql`:

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    country TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    status TEXT CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    total NUMERIC(10, 2),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE inventory (
    product_id INT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    stock INT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

Apply:
```bash
python scripts/setup_schema.py
```

---

### Step 5: Seed realistic data

```bash
python data/seed.py 1000      # quick smoke test
python data/seed.py 10000     # development
python data/seed.py 100000    # regression benchmarks
```

---

## Phase 3 — N+1 Query Detection

### What it is

An N+1 bug fires one query to fetch a list, then one more query per row to load related data — N extra round-trips that scale linearly with result size.

```
SELECT id, user_id FROM orders LIMIT 20           -- 1 query
SELECT email FROM users WHERE id = 1              -- 1 per row
SELECT email FROM users WHERE id = 2
...                                               -- 21 total instead of 1
```

### Running the detector

```bash
python analysis/n_plus_one_detector.py
```

Expected output:

```
=== N+1 Query Detection Demo ===

[BAD]  20 orders fetched → 21 queries fired (1 + 20)
  N+1 candidates detected:
    [20x] SELECT EMAIL FROM USERS WHERE ID = $?

[GOOD] 20 orders+emails fetched → 1 query fired
  No repeated patterns detected.
```

### How it works

`analysis/n_plus_one_detector.py` registers a SQLAlchemy `before_cursor_execute` event listener that records every statement. After a code path runs, `detect(threshold)` normalizes each statement (strips literals) and counts occurrences — any pattern that appears N+ times is a candidate.

### Detecting N+1 in your own code

```python
from analysis.n_plus_one_detector import attach_logger, reset_log, detect
from sqlalchemy import create_engine

engine = create_engine(DB_URL)
attach_logger(engine)

# --- run the suspect code path here ---
reset_log()
your_function(engine)
# --------------------------------------

findings = detect(threshold=5)
for f in findings:
    print(f"[{f['count']}x] {f['query']}")
```

### The fix pattern

| Pattern | Queries | Fix |
|---|---|---|
| Loop + SELECT per row | 1 + N | `JOIN` or `IN (id1, id2, …)` |
| ORM lazy load | 1 + N | `joinedload()` / `selectinload()` |

---

## Phase 4 — Deadlock Simulation

### What it is

A deadlock occurs when two transactions each hold a lock the other needs, creating a cycle that neither can break. PostgreSQL detects the cycle automatically and rolls back one transaction (the "victim").

```
Tx A: locks order 1 ──► tries to lock order 2 ──► BLOCKED (B holds it)
Tx B: locks order 2 ──► tries to lock order 1 ──► BLOCKED (A holds it)
                                                    ▲
                                              PostgreSQL rolls back one
```

### Running the simulator

```bash
python analysis/deadlock_simulator.py
```

Expected output:

```
=== Deadlock Simulator ===

--- Scenario: classic deadlock (reverse lock acquisition order) ---
  Tx A: UPDATE order 1 → UPDATE order 2
  Tx B: UPDATE order 2 → UPDATE order 1
  Starting both transactions concurrently...

  Transaction A: committed
  Transaction B: rolled back — DeadlockDetected

  PostgreSQL detected the cycle and rolled back Transaction B.
  The surviving transaction committed. The rolled-back one can be retried.

--- Prevention ---
  Always acquire locks in a consistent global order across all transactions.
  ...
```

### How it works

`analysis/deadlock_simulator.py` uses `threading.Barrier(2)` to ensure both transactions have acquired their first lock before attempting the second. This makes the deadlock deterministic and reproducible.

### Prevention

The fix is a consistent lock-acquisition order across all code paths:

```python
# Bad — order depends on caller, can deadlock
def update_two_orders(id_a, id_b):
    UPDATE orders WHERE id = id_a
    UPDATE orders WHERE id = id_b

# Good — always process in ascending id order
def update_two_orders(id_a, id_b):
    for oid in sorted([id_a, id_b]):
        UPDATE orders WHERE id = oid
```

---

## Phase 5 — Query Regression Tracking Across Schema Changes

This scenario answers: *"Did my migration make queries faster or slower?"*

It combines three tools: the explain analyzer (plan-level diff), the regression report (latency delta table), and the slow-query pytest gate (CI-safe threshold check).

---

### Step A: Capture a baseline

Seed data, then run the regression report. This saves the first snapshot:

```bash
python data/seed.py 10000
python reports/query_regression_report.py low
```

Output (first run, no previous data):
```
Regression Report — volume: low
No previous run found — this result will be the baseline.
Query            avg ms    p95 ms    max ms  Δ vs last
user_lookup        0.45      0.82      1.20  —
order_history      3.20      5.10      8.40  —
inventory_search   1.10      1.80      2.30  —
```

---

### Step B: Capture EXPLAIN plans before the migration

```bash
python analysis/explain_analyzer.py
```

This saves `reports/plans/order_history_before_index.json` for diff later.

---

### Step C: Apply the migration

```bash
python scripts/setup_schema.py --schema v2_add_indexes/002_add_indexes
```

`migrations/v2_add_indexes/002_add_indexes.sql` adds three indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_orders_user_created
    ON orders(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id
    ON order_items(order_id);

CREATE INDEX IF NOT EXISTS idx_inventory_category_stock
    ON inventory(category, stock) WHERE stock > 0;
```

---

### Step D: Run the regression report again

```bash
python reports/query_regression_report.py low
```

Output (after migration):
```
Regression Report — volume: low
Comparing against last saved run.
Query            avg ms    p95 ms    max ms  Δ vs last
user_lookup        0.42      0.78      1.10  -6.7% ✓
order_history      0.38      0.62      0.95  -88.1% ✓
inventory_search   0.28      0.45      0.70  -74.5% ✓
```

Queries marked `✓` improved by more than 10%. Queries marked `⚠` regressed by more than 20%.

---

### Step E: Slow query threshold gate (pytest)

```bash
pytest benchmarks/test_slow_queries.py -v
```

Each parametrized test asserts that a critical query completes within `SLOW_QUERY_THRESHOLD_MS` (200 ms by default, set in `config.py`). A failing test means a query crossed the threshold — inspect the plan:

```bash
python analysis/explain_analyzer.py
```

---

### Tracking your own migrations

1. Snapshot the baseline: `python reports/query_regression_report.py`
2. Write the migration SQL in `migrations/v<N>_<description>/00N_<description>.sql`
3. Apply: `python scripts/setup_schema.py --schema v<N>_<description>/00N_<description>`
4. Re-run: `python reports/query_regression_report.py`
5. Check gate: `pytest benchmarks/test_slow_queries.py -v`

---

## Phase 6 — Grafana Dashboard

Benchmark results are exported to a `benchmark_results` table in PostgreSQL on every report run. Grafana reads that table via its built-in PostgreSQL datasource.

### Starting Grafana

Grafana is included in the same Compose file. No extra setup is needed:

```bash
docker compose -f docker/docker-compose.yml up -d
```

Open [http://localhost:3000](http://localhost:3000) and log in with `admin / admin`.

The **Query Benchmark Results** dashboard and the **Benchmark DB** datasource are auto-provisioned from:

```
docker/grafana/
├── provisioning/
│   ├── datasources/postgres.yml   # connects to the postgres service
│   └── dashboards/dashboard.yml   # points Grafana at the dashboard folder
└── dashboards/benchmark.json      # the actual dashboard
```

### Dashboard panels

| Panel | SQL column | Use |
|---|---|---|
| Avg Latency Over Time | `avg_ms` | Spot regressions across benchmark runs |
| P95 Latency Over Time | `p95_ms` | Catch tail latency spikes after migrations |
| Latest Benchmark Run | all columns | Quick snapshot of the most recent run |

The **Volume** dropdown at the top filters all panels to `low`, `medium`, or `high`.

### How data gets in

`query_regression_report.py` calls `reports/export_metrics.py` after every run. The exporter creates `benchmark_results` if it doesn't exist, then inserts one row per query per run:

```python
from reports.export_metrics import export
export("low", results)
```

To backfill Grafana from previously saved JSON files (e.g. runs made before Grafana was set up):

```bash
python reports/export_metrics.py
```

---

## Quick Reference

```bash
# Start database + Grafana
docker compose -f docker/docker-compose.yml up -d
# Open Grafana → http://localhost:3000  (admin / admin)

# Seed data
python data/seed.py 10000

# --- N+1 Detection ---
python analysis/n_plus_one_detector.py

# --- Deadlock Simulation ---
python analysis/deadlock_simulator.py

# --- Query Regression Tracking ---
# 1. Baseline
python reports/query_regression_report.py low

# 2. Capture EXPLAIN plan
python analysis/explain_analyzer.py

# 3. Apply migration
python scripts/setup_schema.py --schema v2_add_indexes/002_add_indexes

# 4. Measure impact
python reports/query_regression_report.py low

# 5. Threshold gate
pytest benchmarks/test_slow_queries.py -v
```

---

## Deliverable Checklist

| Deliverable | Status |
|---|---|
| Dockerized PostgreSQL with `pg_stat_statements` | ✅ |
| Deterministic data generator (1K / 10K / 100K / 1M) | ✅ |
| N+1 detector with bad/good simulation | ✅ |
| Deadlock simulator with mitigation guide | ✅ |
| EXPLAIN ANALYZE plan capture & diff | ✅ |
| Query regression report with Δ vs previous run | ✅ |
| Schema migration v2 (indexes) for regression demo | ✅ |
| Slow query threshold tests (pytest) | ✅ |
| Grafana dashboard with auto-provisioned datasource | ✅ |
| Metrics exporter to `benchmark_results` table | ✅ |

---

## References

- [PostgreSQL EXPLAIN documentation](https://www.postgresql.org/docs/current/sql-explain.html)
- [PostgreSQL deadlock detection](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS)
- [Use The Index, Luke — query optimization](https://use-the-index-luke.com/)
- [pgbench](https://www.postgresql.org/docs/current/pgbench.html)
- [Grafana PostgreSQL datasource docs](https://grafana.com/docs/grafana/latest/datasources/postgres/)
