# Database Performance Testing Suite — Step-by-Step Implementation Guide

**Project:** db-performance-tests  
**Estimated duration:** 4–5 weeks  
**Complexity:** 4/5

---

## Phase 1 — Environment Setup (Week 1, Days 1–2)

### Step 1: Initialize the project structure

```bash
mkdir -p db-performance-tests/{benchmarks/{queries,scenarios},analysis,data,migrations/baseline,reports,docker}
cd db-performance-tests
git init
touch README.md .gitignore
```

Add to `.gitignore`:
```
__pycache__/
*.pyc
.env
reports/output/
data/generated/
```

---

### Step 2: Set up the Dockerized database

Create `docker/docker-compose.yml`:

```yaml
version: "3.9"
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

Create `docker/init.sql` with `pg_stat_statements` extension:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Start the container and verify:

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml exec postgres psql -U perftest -d perfdb -c "SELECT version();"
```

---

### Step 3: Set up the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install psycopg2-binary sqlalchemy faker pytest python-dotenv tabulate
pip freeze > requirements.txt
```

Create `.env`:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=perfdb
DB_USER=perftest
DB_PASSWORD=perftest
```

Create `config.py` at the project root:

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

## Phase 2 — Schema & Realistic Data Generation (Week 1, Days 3–5)

### Step 4: Define the baseline schema

Create `migrations/baseline/001_initial_schema.sql`:

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

Apply the schema:
```bash
docker compose -f docker/docker-compose.yml exec -T postgres \
  psql -U perftest -d perfdb < migrations/baseline/001_initial_schema.sql
```

Snapshot current schema for regression comparison:
```bash
docker compose -f docker/docker-compose.yml exec postgres \
  pg_dump -U perftest -d perfdb --schema-only > migrations/baseline/schema_v1.sql
```

---

### Step 5: Define production-like data distributions

Create `data/distributions.json`:

```json
{
  "users": {
    "countries": {"BR": 0.35, "US": 0.25, "DE": 0.15, "IN": 0.15, "OTHER": 0.10}
  },
  "orders": {
    "status": {"paid": 0.55, "shipped": 0.25, "cancelled": 0.12, "pending": 0.08},
    "items_per_order": {"min": 1, "max": 8, "avg": 2.5}
  },
  "inventory": {
    "categories": {"electronics": 0.30, "clothing": 0.25, "food": 0.20, "books": 0.15, "other": 0.10}
  }
}
```

---

### Step 6: Build the deterministic data generator

Create `data/seed.py`:

```python
import random
import json
from faker import Faker
from sqlalchemy import create_engine, text
from config import DB_URL

SEED = 42
fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

with open("data/distributions.json") as f:
    DIST = json.load(f)

def weighted_choice(distribution: dict) -> str:
    keys = list(distribution.keys())
    weights = list(distribution.values())
    return random.choices(keys, weights=weights, k=1)[0]

def generate(engine, n_users: int):
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE order_items, orders, users, inventory RESTART IDENTITY CASCADE"
        ))

        # Users
        users = [
            {"email": fake.unique.email(), "country": weighted_choice(DIST["users"]["countries"])}
            for _ in range(n_users)
        ]
        conn.execute(text(
            "INSERT INTO users (email, country) VALUES (:email, :country)"
        ), users)

        # Inventory
        products = [
            {
                "product_id": i,
                "name": fake.word().title(),
                "category": weighted_choice(DIST["inventory"]["categories"]),
                "stock": random.randint(0, 500),
            }
            for i in range(1, 501)
        ]
        conn.execute(text(
            "INSERT INTO inventory (product_id, name, category, stock) "
            "VALUES (:product_id, :name, :category, :stock)"
        ), products)

        # Orders and items
        n_orders = int(n_users * 2.5)
        for order_num in range(1, n_orders + 1):
            user_id = random.randint(1, n_users)
            status = weighted_choice(DIST["orders"]["status"])
            total = 0
            conn.execute(text(
                "INSERT INTO orders (id, user_id, status, total) "
                "VALUES (:id, :user_id, :status, 0)"
            ), {"id": order_num, "user_id": user_id, "status": status})

            n_items = random.randint(
                DIST["orders"]["items_per_order"]["min"],
                DIST["orders"]["items_per_order"]["max"]
            )
            items = []
            for _ in range(n_items):
                price = round(random.uniform(5, 500), 2)
                qty = random.randint(1, 5)
                total += price * qty
                items.append({
                    "order_id": order_num,
                    "product_id": random.randint(1, 500),
                    "quantity": qty,
                    "price": price,
                })
            conn.execute(text(
                "INSERT INTO order_items (order_id, product_id, quantity, price) "
                "VALUES (:order_id, :product_id, :quantity, :price)"
            ), items)
            conn.execute(text(
                "UPDATE orders SET total = :total WHERE id = :id"
            ), {"total": round(total, 2), "id": order_num})

    print(f"Seeded {n_users} users, {n_orders} orders.")


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    engine = create_engine(DB_URL)
    generate(engine, n)
```

Test each volume level:
```bash
python data/seed.py 1000      # 1K
python data/seed.py 10000     # 10K
python data/seed.py 100000    # 100K
python data/seed.py 1000000   # 1M — takes several minutes
```

---

## Phase 3 — Benchmark Suite (Week 2)

### Step 7: Write the critical query files

Create `benchmarks/queries/user-lookup.sql`:
```sql
SELECT id, email, country FROM users WHERE email = :email;
```

Create `benchmarks/queries/order-history.sql`:
```sql
SELECT o.id, o.status, o.total, o.created_at
FROM orders o
WHERE o.user_id = :user_id
ORDER BY o.created_at DESC
LIMIT 20;
```

Create `benchmarks/queries/inventory-search.sql`:
```sql
SELECT product_id, name, stock
FROM inventory
WHERE category = :category AND stock > 0
ORDER BY stock DESC
LIMIT 50;
```

Add at least 7 more queries covering JOIN-heavy paths, aggregations, and subqueries.

---

### Step 8: Build the volume benchmark scenarios

Create `benchmarks/scenarios/run_benchmark.py`:

```python
import time
import statistics
import random
from sqlalchemy import create_engine, text
from config import DB_URL
from data.seed import generate

VOLUMES = {"low": 1_000, "medium": 100_000, "high": 1_000_000}
ITERATIONS = 50

QUERIES = {
    "user_lookup": (
        "SELECT id, email, country FROM users WHERE email = :p",
        lambda conn: {"p": conn.execute(text("SELECT email FROM users ORDER BY random() LIMIT 1")).scalar()}
    ),
    "order_history": (
        "SELECT o.id, o.status, o.total FROM orders o WHERE o.user_id = :p ORDER BY o.created_at DESC LIMIT 20",
        lambda conn: {"p": random.randint(1, conn.execute(text("SELECT count(*) FROM users")).scalar())}
    ),
    "inventory_search": (
        "SELECT product_id, name, stock FROM inventory WHERE category = :p AND stock > 0 LIMIT 50",
        lambda conn: {"p": random.choice(["electronics", "clothing", "food", "books", "other"])}
    ),
}

def benchmark_query(engine, label: str, sql: str, param_fn, iterations: int = ITERATIONS):
    times = []
    with engine.connect() as conn:
        for _ in range(iterations):
            params = param_fn(conn)
            start = time.perf_counter()
            conn.execute(text(sql), params)
            times.append((time.perf_counter() - start) * 1000)
    return {
        "query": label,
        "min_ms": round(min(times), 2),
        "avg_ms": round(statistics.mean(times), 2),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 2),
        "max_ms": round(max(times), 2),
    }

def run_all(volume_label: str):
    n_rows = VOLUMES[volume_label]
    engine = create_engine(DB_URL)
    print(f"\n=== Volume: {volume_label} ({n_rows:,} users) ===")
    generate(engine, n_rows)
    results = []
    for label, (sql, param_fn) in QUERIES.items():
        result = benchmark_query(engine, label, sql, param_fn)
        results.append(result)
        print(f"  {label}: avg={result['avg_ms']}ms  p95={result['p95_ms']}ms")
    return results


if __name__ == "__main__":
    import sys
    volume = sys.argv[1] if len(sys.argv) > 1 else "low"
    run_all(volume)
```

Run benchmarks:
```bash
python benchmarks/scenarios/run_benchmark.py low
python benchmarks/scenarios/run_benchmark.py medium
python benchmarks/scenarios/run_benchmark.py high
```

---

## Phase 4 — Analysis Tools (Week 3)

### Step 9: Build the EXPLAIN ANALYZE plan comparator

Create `analysis/explain-analyzer.py`:

```python
import json
from sqlalchemy import create_engine, text
from config import DB_URL

engine = create_engine(DB_URL)

def explain(sql: str, params: dict = {}) -> dict:
    with engine.connect() as conn:
        result = conn.execute(
            text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"), params
        )
        return result.fetchone()[0][0]

def compare(label: str, sql: str, params: dict = {}):
    plan = explain(sql, params)
    node = plan["Plan"]
    print(f"\n--- {label} ---")
    print(f"  Total cost:      {node['Total Cost']}")
    print(f"  Actual rows:     {node['Actual Rows']}")
    print(f"  Actual time ms:  {node['Actual Total Time']:.2f}")
    print(f"  Node type:       {node['Node Type']}")
    if "Plans" in node:
        for child in node["Plans"]:
            print(f"    └─ {child['Node Type']} (rows={child['Actual Rows']})")
    return plan

def save_plan(plan: dict, filename: str):
    with open(f"reports/{filename}.json", "w") as f:
        json.dump(plan, f, indent=2)

if __name__ == "__main__":
    # Before index
    plan_before = compare(
        "order_history — no index",
        "SELECT id, status, total FROM orders WHERE user_id = :uid ORDER BY created_at DESC LIMIT 20",
        {"uid": 42}
    )
    save_plan(plan_before, "plan_before_index")

    # Create index
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id, created_at DESC)"))

    # After index
    plan_after = compare(
        "order_history — with index",
        "SELECT id, status, total FROM orders WHERE user_id = :uid ORDER BY created_at DESC LIMIT 20",
        {"uid": 42}
    )
    save_plan(plan_after, "plan_after_index")
```

Run before and after a schema migration to capture diff:
```bash
python analysis/explain-analyzer.py
```

---

### Step 10: Build the N+1 query detector

Create `analysis/n-plus-one-detector.py`:

```python
import re
from collections import defaultdict
from sqlalchemy import create_engine, text, event
from config import DB_URL

_query_log: list[str] = []

def attach_logger(engine):
    @event.listens_for(engine, "before_cursor_execute")
    def log_query(conn, cursor, statement, parameters, context, executemany):
        _query_log.append(statement.strip())

def normalize(sql: str) -> str:
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"=\s*\$\d+", "= ?", sql)
    sql = re.sub(r"IN\s*\([^)]+\)", "IN (?)", sql)
    return sql.upper().strip()

def detect_n_plus_one(threshold: int = 5) -> list[dict]:
    counts = defaultdict(int)
    for q in _query_log:
        counts[normalize(q)] += 1
    return [
        {"query": q, "count": c}
        for q, c in sorted(counts.items(), key=lambda x: -x[1])
        if c >= threshold
    ]

def simulate_n_plus_one(engine, user_ids: list[int]):
    with engine.connect() as conn:
        orders = conn.execute(
            text("SELECT id, user_id FROM orders WHERE user_id = ANY(:ids)"),
            {"ids": user_ids}
        ).fetchall()

        # Intentional N+1: fetching user for each order separately
        for order in orders:
            conn.execute(
                text("SELECT email FROM users WHERE id = :uid"),
                {"uid": order.user_id}
            )

if __name__ == "__main__":
    engine = create_engine(DB_URL)
    attach_logger(engine)

    with engine.connect() as conn:
        ids = [r[0] for r in conn.execute(text("SELECT id FROM users LIMIT 20")).fetchall()]

    simulate_n_plus_one(engine, ids)

    findings = detect_n_plus_one(threshold=3)
    print(f"\nN+1 candidates (>= 3 repeated calls):")
    for f in findings:
        print(f"  [{f['count']}x] {f['query'][:120]}")
```

---

### Step 11: Build the deadlock simulator

Create `analysis/deadlock-simulator.py`:

```python
import threading
import time
from sqlalchemy import create_engine, text
from config import DB_URL

def transaction_a(engine, result: dict):
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE orders SET status='pending' WHERE id=1"))
            time.sleep(0.3)  # hold lock, give B time to grab its lock
            conn.execute(text("UPDATE orders SET status='paid' WHERE id=2"))
            result["a"] = "committed"
    except Exception as e:
        result["a"] = f"deadlock/rollback: {e}"

def transaction_b(engine, result: dict):
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE orders SET status='pending' WHERE id=2"))
            time.sleep(0.3)
            conn.execute(text("UPDATE orders SET status='paid' WHERE id=1"))
            result["b"] = "committed"
    except Exception as e:
        result["b"] = f"deadlock/rollback: {e}"

def run():
    engine = create_engine(DB_URL, pool_size=5)
    result = {}
    ta = threading.Thread(target=transaction_a, args=(engine, result))
    tb = threading.Thread(target=transaction_b, args=(engine, result))

    print("Starting concurrent transactions (deadlock expected)...")
    ta.start()
    time.sleep(0.05)
    tb.start()
    ta.join()
    tb.join()

    print(f"\nTransaction A: {result.get('a')}")
    print(f"Transaction B: {result.get('b')}")
    print("\nResolution: PostgreSQL auto-detects deadlocks and rolls back one transaction.")
    print("Mitigation: always acquire locks in a consistent global order.")

if __name__ == "__main__":
    run()
```

---

## Phase 5 — Index Effectiveness Tests (Week 3–4)

### Step 12: Write index effectiveness test suite

Create `benchmarks/scenarios/index_effectiveness.py`:

```python
from sqlalchemy import create_engine, text
from analysis.explain_analyzer import compare, save_plan
from config import DB_URL

SCENARIOS = [
    {
        "label": "user_by_country",
        "sql": "SELECT id, email FROM users WHERE country = :p",
        "params": {"p": "BR"},
        "index_ddl": "CREATE INDEX idx_users_country ON users(country)",
        "drop_ddl": "DROP INDEX IF EXISTS idx_users_country",
    },
    {
        "label": "inventory_by_category",
        "sql": "SELECT product_id, name FROM inventory WHERE category = :p AND stock > 0",
        "params": {"p": "electronics"},
        "index_ddl": "CREATE INDEX idx_inventory_cat_stock ON inventory(category, stock)",
        "drop_ddl": "DROP INDEX IF EXISTS idx_inventory_cat_stock",
    },
    {
        "label": "orders_by_status",
        "sql": "SELECT id, total FROM orders WHERE status = :p ORDER BY created_at DESC LIMIT 100",
        "params": {"p": "paid"},
        "index_ddl": "CREATE INDEX idx_orders_status ON orders(status, created_at DESC)",
        "drop_ddl": "DROP INDEX IF EXISTS idx_orders_status",
    },
]

def run():
    engine = create_engine(DB_URL)
    for s in SCENARIOS:
        with engine.begin() as conn:
            conn.execute(text(s["drop_ddl"]))

        plan_before = compare(f"{s['label']} — no index", s["sql"], s["params"])
        save_plan(plan_before, f"{s['label']}_before")

        with engine.begin() as conn:
            conn.execute(text(s["index_ddl"]))

        plan_after = compare(f"{s['label']} — with index", s["sql"], s["params"])
        save_plan(plan_after, f"{s['label']}_after")

if __name__ == "__main__":
    run()
```

---

## Phase 6 — Regression Tracking (Week 4)

### Step 13: Build the query regression report

Create `reports/query-regression-report.py`:

```python
import json
import os
from datetime import datetime
from tabulate import tabulate
from benchmarks.scenarios.run_benchmark import run_all, VOLUMES

RESULTS_DIR = "reports/output"
os.makedirs(RESULTS_DIR, exist_ok=True)

def load_previous(volume: str) -> dict | None:
    path = f"{RESULTS_DIR}/{volume}_latest.json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def save_results(volume: str, results: list[dict]):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    with open(f"{RESULTS_DIR}/{volume}_{ts}.json", "w") as f:
        json.dump(results, f, indent=2)
    with open(f"{RESULTS_DIR}/{volume}_latest.json", "w") as f:
        json.dump(results, f, indent=2)

def compare(current: list[dict], previous: list[dict] | None) -> list[list]:
    prev_map = {r["query"]: r for r in (previous or [])}
    rows = []
    for r in current:
        prev = prev_map.get(r["query"])
        delta = ""
        if prev:
            diff = r["avg_ms"] - prev["avg_ms"]
            pct = (diff / prev["avg_ms"]) * 100
            delta = f"{'+' if diff > 0 else ''}{pct:.1f}%"
        rows.append([r["query"], r["avg_ms"], r["p95_ms"], r["max_ms"], delta or "—"])
    return rows

def run():
    for volume in VOLUMES:
        current = run_all(volume)
        previous = load_previous(volume)
        save_results(volume, current)

        print(f"\n=== Regression Report: {volume} ===")
        rows = compare(current, previous)
        print(tabulate(rows, headers=["Query", "avg ms", "p95 ms", "max ms", "Δ vs last"]))

if __name__ == "__main__":
    run()
```

---

## Phase 7 — CI Integration (Week 4–5)

### Step 14: Set up the slow query threshold test

Create `benchmarks/test_slow_queries.py` (runs with `pytest`):

```python
import pytest
from sqlalchemy import create_engine, text
import time
from config import DB_URL, SLOW_QUERY_THRESHOLD_MS

engine = create_engine(DB_URL)

CRITICAL_QUERIES = [
    ("user_lookup", "SELECT id FROM users WHERE email = (SELECT email FROM users LIMIT 1)"),
    ("order_history", "SELECT id FROM orders WHERE user_id = 1 ORDER BY created_at DESC LIMIT 20"),
    ("inventory_search", "SELECT product_id FROM inventory WHERE category = 'electronics' AND stock > 0 LIMIT 50"),
]

@pytest.mark.parametrize("label,sql", CRITICAL_QUERIES)
def test_query_within_threshold(label: str, sql: str):
    with engine.connect() as conn:
        start = time.perf_counter()
        conn.execute(text(sql))
        elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < SLOW_QUERY_THRESHOLD_MS, (
        f"{label} took {elapsed_ms:.1f}ms — exceeds threshold of {SLOW_QUERY_THRESHOLD_MS}ms"
    )
```

Run:
```bash
pytest benchmarks/test_slow_queries.py -v
```

---

### Step 15: Create the CI workflow

Create `.github/workflows/db-benchmarks.yml`:

```yaml
name: DB Performance Benchmarks

on:
  pull_request:
    paths:
      - "migrations/**"
      - "benchmarks/**"
      - "analysis/**"

jobs:
  benchmark:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: perftest
          POSTGRES_PASSWORD: perftest
          POSTGRES_DB: perfdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Apply schema
        run: |
          psql postgresql://perftest:perftest@localhost:5432/perfdb \
            -f migrations/baseline/001_initial_schema.sql

      - name: Seed test data (medium volume)
        run: python data/seed.py 10000
        env:
          DB_HOST: localhost

      - name: Run slow query threshold tests
        run: pytest benchmarks/test_slow_queries.py -v
        env:
          DB_HOST: localhost

      - name: Run regression report
        run: python reports/query-regression-report.py
        env:
          DB_HOST: localhost

      - name: Upload benchmark results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: reports/output/
          retention-days: 90
```

---

## Phase 8 — Grafana Dashboard (Week 5)

### Step 16: Add Grafana and Prometheus to Docker Compose

Extend `docker/docker-compose.yml`:

```yaml
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - grafana_data:/var/lib/grafana

volumes:
  pgdata:
  grafana_data:
```

### Step 17: Export benchmark results to Grafana

Create `reports/export_metrics.py` to write results to a Postgres metrics table that Grafana reads via its PostgreSQL data source:

```python
from sqlalchemy import create_engine, text
from config import DB_URL

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS benchmark_results (
    id SERIAL PRIMARY KEY,
    run_at TIMESTAMPTZ DEFAULT now(),
    volume TEXT,
    query_label TEXT,
    avg_ms FLOAT,
    p95_ms FLOAT,
    max_ms FLOAT
);
"""

def export(volume: str, results: list[dict]):
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        conn.execute(
            text(
                "INSERT INTO benchmark_results (volume, query_label, avg_ms, p95_ms, max_ms) "
                "VALUES (:volume, :query, :avg_ms, :p95_ms, :max_ms)"
            ),
            [{"volume": volume, **r} for r in results]
        )
    print(f"Exported {len(results)} results for volume={volume}")
```

### Step 18: Configure Grafana

1. Open Grafana at `http://localhost:3000` (admin/admin).
2. Add PostgreSQL as a data source pointing to the `postgres` service.
3. Create a dashboard with a time-series panel using this query:
   ```sql
   SELECT run_at AS time, avg_ms, query_label
   FROM benchmark_results
   WHERE volume = 'medium'
   ORDER BY run_at
   ```
4. Add panels for p95 latency and max latency per query across runs.
5. Export the dashboard JSON to `docker/grafana-dashboard.json` for version control.

---

## Final Checklist

| Deliverable | Status |
| --- | --- |
| Dockerized PostgreSQL with `pg_stat_statements` | [ ] |
| Deterministic data generator (1K / 10K / 100K / 1M rows) | [ ] |
| Benchmark suite for 10+ queries across 4 volumes | [ ] |
| EXPLAIN ANALYZE before/after index comparator | [ ] |
| N+1 query detector with example simulation | [ ] |
| Deadlock simulator with documented resolution | [ ] |
| Index effectiveness tests for 3+ scenarios | [ ] |
| Slow query threshold tests (`pytest`) | [ ] |
| Query regression report with delta vs. previous run | [ ] |
| CI workflow triggering on migration PRs | [ ] |
| Grafana dashboard tracking latency over schema versions | [ ] |

---

## Quick Reference: Key Commands

```bash
# Start database
docker compose -f docker/docker-compose.yml up -d

# Seed data
python data/seed.py 10000

# Run benchmarks
python benchmarks/scenarios/run_benchmark.py medium

# Detect N+1 patterns
python analysis/n-plus-one-detector.py

# Simulate deadlock
python analysis/deadlock-simulator.py

# Compare EXPLAIN plans before/after index
python analysis/explain-analyzer.py

# Run index effectiveness tests
python benchmarks/scenarios/index_effectiveness.py

# Run slow query tests
pytest benchmarks/test_slow_queries.py -v

# Generate regression report
python reports/query-regression-report.py
```

---

## References

- [PostgreSQL EXPLAIN documentation](https://www.postgresql.org/docs/current/sql-explain.html)
- [pgbench — PostgreSQL benchmarking](https://www.postgresql.org/docs/current/pgbench.html)
- [Percona Toolkit pt-query-digest](https://docs.percona.com/percona-toolkit/pt-query-digest.html)
- [Use The Index, Luke — query optimization](https://use-the-index-luke.com/)
