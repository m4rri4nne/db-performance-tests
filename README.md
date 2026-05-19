# 🐘 Database Performance Tests

![Status](https://img.shields.io/badge/status-in%20progress-yellow?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-required-2496ED?style=flat-square&logo=docker&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-dashboard-F46800?style=flat-square&logo=grafana&logoColor=white)
![pytest](https://img.shields.io/badge/tested%20with-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)

A PostgreSQL performance testing suite for measuring query latency, detecting N+1 patterns, simulating deadlocks, and tracking regressions across schema versions.

---

## 📖 Overview

The project runs a Dockerized **PostgreSQL 16** instance with `pg_stat_statements` enabled and populates it with deterministic, production-like data (up to 1M rows). A benchmark suite measures critical query performance across four data volumes, and an analysis layer compares `EXPLAIN ANALYZE` plans before and after index changes. Results feed into a regression report and a **Grafana** dashboard.

**Schema:** `users` → `orders` → `order_items` + `inventory`

---

## ✅ Prerequisites

- 🐳 Docker + Docker Compose
- 🐍 Python 3.10+

---

## 🚀 Setup

**1. Start the database**

```bash
docker compose -f docker/docker-compose.yml up -d
```

**2. Create a virtual environment and install dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Configure environment variables**

Create a `.env` file at the project root:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=perfdb
DB_USER=perftest
DB_PASSWORD=perftest
```

**4. Apply the schema**

```bash
docker compose -f docker/docker-compose.yml exec -T postgres \
  psql -U perftest -d perfdb < migrations/baseline/001_initial_schema.sql
```

---

## 🧪 Usage

All scripts are run from the **project root**.

### 🌱 Seed data

```bash
python data/seed.py 1000      # 1K users (~2.5K orders)
python data/seed.py 10000     # 10K
python data/seed.py 100000    # 100K
python data/seed.py 1000000   # 1M — takes several minutes
```

Each run truncates all tables first. The seed is deterministic (`SEED = 42`), so the same row count always produces the same data.

### ⚡ Run benchmarks

```bash
python benchmarks/scenarios/run_benchmark.py low     # 1K users
python benchmarks/scenarios/run_benchmark.py medium  # 100K users
python benchmarks/scenarios/run_benchmark.py high    # 1M users
```

Outputs `min`, `avg`, `p95`, and `max` latency (ms) for each query.

### 🔍 Analyze query plans

```bash
python analysis/explain-analyzer.py
```

Runs `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` before and after creating an index and saves the plans to `reports/`.

### 🔁 Detect N+1 queries

```bash
python analysis/n-plus-one-detector.py
```

Instruments the SQLAlchemy engine and flags any normalized query executed 5+ times in a single logical operation.

### 💥 Simulate a deadlock

```bash
python analysis/deadlock-simulator.py
```

Spawns two concurrent transactions that acquire locks in opposing order. PostgreSQL detects and rolls one back automatically.

### 📊 Test index effectiveness

```bash
python benchmarks/scenarios/index_effectiveness.py
```

Drops, benchmarks, creates, and re-benchmarks indexes for three scenarios: user lookup by country, inventory search by category, and orders by status.

### 🐢 Slow query threshold tests (pytest)

```bash
pytest benchmarks/test_slow_queries.py -v
```

Fails if any critical query exceeds `SLOW_QUERY_THRESHOLD_MS` (default: 200ms), as defined in `config.py`.

### 📈 Query regression report

```bash
python reports/query-regression-report.py
```

Runs all benchmark volumes, compares against the previous run saved in `reports/output/`, and prints a delta table (`Δ vs last`).

---

## 🗂️ Project Structure

```
.
├── config.py                          # DB_URL and threshold config (reads .env)
├── data/
│   ├── seed.py                        # Deterministic data generator
│   └── distributions.json             # Country, order status, category weights
├── migrations/
│   └── baseline/
│       ├── 001_initial_schema.sql     # Table definitions
│       └── schema_v1.sql              # Schema snapshot for regression comparison
├── benchmarks/
│   ├── queries/                       # Raw .sql files for critical paths
│   ├── scenarios/
│   │   ├── run_benchmark.py           # Volume benchmark runner
│   │   └── index_effectiveness.py    # Before/after index comparison
│   └── test_slow_queries.py          # pytest threshold tests
├── analysis/
│   ├── explain-analyzer.py            # EXPLAIN ANALYZE plan comparator
│   ├── n-plus-one-detector.py        # N+1 pattern detector
│   └── deadlock-simulator.py         # Concurrent transaction deadlock demo
├── reports/
│   ├── query-regression-report.py    # Regression diff report
│   ├── export_metrics.py             # Writes results to DB for Grafana
│   └── output/                       # Generated JSON result files
└── docker/
    ├── docker-compose.yml             # PostgreSQL 16 + Grafana
    └── init.sql                       # pg_stat_statements extension
```

---

## 📡 Grafana Dashboard

Grafana is available at `http://localhost:3000` (admin/admin) after adding it to the Compose file. It reads from a `benchmark_results` table populated by `reports/export_metrics.py` and tracks `avg_ms`, `p95_ms`, and `max_ms` per query over time.

---

## ⚙️ CI

The GitHub Actions workflow at `.github/workflows/db-benchmarks.yml` triggers on pull requests that touch `migrations/`, `benchmarks/`, or `analysis/`. It spins up PostgreSQL as a service, seeds 10K rows, runs the pytest threshold tests, and uploads benchmark results as an artifact.
