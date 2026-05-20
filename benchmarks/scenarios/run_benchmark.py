import sys
import time
import statistics
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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