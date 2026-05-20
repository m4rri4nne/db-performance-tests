# Database Performance Tests

![Status](https://img.shields.io/badge/status-in%20progress-yellow?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-required-2496ED?style=flat-square&logo=docker&logoColor=white)
![pytest](https://img.shields.io/badge/tested%20with-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-dashboard-F46800?style=flat-square&logo=grafana&logoColor=white)

A PostgreSQL performance testing suite focused on three scenarios:

- **N+1 Query Detection** — instrument queries, surface repeated patterns, compare bad vs. fixed implementations
- **Deadlock Simulation** — reproduce the classic reverse lock-order deadlock and document the fix
- **Query Regression Tracking Across Schema Changes** — benchmark before and after a migration, diff execution plans, gate on latency thresholds with pytest

**Schema:** `users` → `orders` → `order_items` + `inventory`

---

## Prerequisites

- Docker + Docker Compose
- Python 3.10+

---

## Setup

**1. Start the database**

```bash
docker compose -f docker/docker-compose.yml up -d
```

**2. Create virtual environment and install dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Configure environment variables**

Create `.env` at the project root:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=perfdb
DB_USER=perftest
DB_PASSWORD=perftest
```

**4. Apply the schema and seed data**

```bash
python scripts/setup_schema.py
python data/seed.py 10000
```

---

## Scenarios

### N+1 Query Detection

```bash
python analysis/n_plus_one_detector.py
```

Attaches a SQLAlchemy event listener, runs a simulated N+1 code path (one query per order row), then the fixed version (single JOIN). Prints a count of repeated normalized queries so the pattern is unmistakable.

```
[BAD]  20 orders fetched → 21 queries fired (1 + 20)
  N+1 candidates detected:
    [20x] SELECT EMAIL FROM USERS WHERE ID = $?

[GOOD] 20 orders+emails fetched → 1 query fired
```

To instrument your own code, import `attach_logger`, `reset_log`, and `detect` from `analysis/n_plus_one_detector.py`.

---

### Deadlock Simulation

```bash
python analysis/deadlock_simulator.py
```

Spawns two threads that acquire row locks in opposite order using a `threading.Barrier` to make the deadlock deterministic. PostgreSQL detects the cycle and rolls back one transaction automatically. The script prints which transaction was the victim and shows the consistent lock-ordering fix.

```
Transaction A: committed
Transaction B: rolled back — DeadlockDetected

PostgreSQL detected the cycle and rolled back Transaction B.
```

---

### Query Regression Tracking Across Schema Changes

The workflow is: baseline → capture plan → migrate → measure impact → pytest gate.

**1. Capture baseline performance**

```bash
python reports/query_regression_report.py low
```

**2. Capture EXPLAIN plan before migration**

```bash
python analysis/explain_analyzer.py
```

Plans are saved as JSON to `reports/plans/`.

**3. Apply migration**

```bash
python scripts/setup_schema.py --schema v2_add_indexes/002_add_indexes
```

**4. Measure the impact**

```bash
python reports/query_regression_report.py low
```

```
Query            avg ms    p95 ms    max ms  Δ vs last
order_history      0.38      0.62      0.95  -88.1% ✓
inventory_search   0.28      0.45      0.70  -74.5% ✓
```

Queries that regressed by more than 20% are flagged with `⚠`.

**5. Latency threshold gate**

```bash
pytest benchmarks/test_slow_queries.py -v
```

Fails if any critical query exceeds `SLOW_QUERY_THRESHOLD_MS` (200 ms, set in `config.py`).

---

## Grafana Dashboard

Benchmark results are automatically exported to a `benchmark_results` table in PostgreSQL and visualized in Grafana.

**Start Grafana:**

```bash
docker compose -f docker/docker-compose.yml up -d
```

Open [http://localhost:3000](http://localhost:3000) — login `admin / admin`.

The **Query Benchmark Results** dashboard loads automatically. No manual setup needed: the PostgreSQL datasource and dashboard are provisioned on startup.

**Panels:**

| Panel | What it shows |
|---|---|
| Avg Latency Over Time | avg_ms per query, color-coded — turns yellow at 100 ms, red at 200 ms |
| P95 Latency Over Time | p95_ms per query — highlights tail latency spikes across migrations |
| Latest Benchmark Run | Table of the most recent run: avg / p95 / max per query |

Use the **Volume** dropdown at the top to switch between `low`, `medium`, and `high` data sets.

Every time you run the regression report, results are written to the table automatically:

```bash
python reports/query_regression_report.py low
# → runs benchmarks, saves JSON, exports to benchmark_results, prints delta table
```

To backfill Grafana from previously saved JSON files:

```bash
python reports/export_metrics.py
```

---

## Seeding data

```bash
python data/seed.py 1000      # quick smoke test
python data/seed.py 10000     # development
python data/seed.py 100000    # regression benchmarks
```

Each run truncates all tables. The seed is deterministic (`SEED = 42`).

---

## Project Structure

```
.
├── config.py
├── analysis/
│   ├── n_plus_one_detector.py     # N+1 detection and simulation
│   ├── deadlock_simulator.py      # Concurrent deadlock demo
│   └── explain_analyzer.py        # EXPLAIN plan capture and diff
├── benchmarks/
│   ├── queries/                   # Raw .sql files
│   ├── scenarios/
│   │   └── run_benchmark.py       # Volume benchmark runner
│   └── test_slow_queries.py       # pytest latency threshold gate
├── data/
│   ├── seed.py
│   └── distributions.json
├── migrations/
│   ├── baseline/
│   │   └── 001_initial_schema.sql
│   └── v2_add_indexes/
│       └── 002_add_indexes.sql    # Sample migration for regression demo
├── reports/
│   ├── query_regression_report.py # Delta reporter (also exports to Grafana)
│   ├── export_metrics.py          # Writes results to benchmark_results table
│   ├── output/                    # Timestamped benchmark JSON results
│   └── plans/                     # Saved EXPLAIN plans
├── scripts/
│   └── setup_schema.py
└── docker/
    ├── docker-compose.yml         # PostgreSQL + Grafana
    ├── init.sql
    └── grafana/
        ├── provisioning/
        │   ├── datasources/postgres.yml
        │   └── dashboards/dashboard.yml
        └── dashboards/benchmark.json  # Auto-provisioned dashboard
```

---

## References

- [PostgreSQL EXPLAIN documentation](https://www.postgresql.org/docs/current/sql-explain.html)
- [PostgreSQL deadlock detection](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS)
- [Use The Index, Luke](https://use-the-index-luke.com/)
