import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "docker" / "docker-compose.yml"

COMPOSE = ["docker", "compose", "-f", str(COMPOSE_FILE)]


def run(cmd, **kwargs):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        sys.exit(result.returncode)


def apply_schema(migration: Path, user: str, dbname: str):
    print("\n--- Applying schema ---")
    with migration.open("rb") as sql_file:
        run(
            COMPOSE + ["exec", "-T", "postgres", "psql", "-U", user, "-d", dbname],
            stdin=sql_file,
        )


def snapshot_schema(snapshot: Path, user: str, dbname: str):
    print("\n--- Snapshotting schema ---")
    result = subprocess.run(
        COMPOSE + ["exec", "postgres", "pg_dump", "-U", user, "-d", dbname, "--schema-only"],
        capture_output=True,
    )
    if result.returncode != 0:
        print(result.stderr.decode())
        sys.exit(result.returncode)
    snapshot.write_bytes(result.stdout)
    print(f"Schema snapshot saved to {snapshot.relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply and snapshot a database schema.")
    parser.add_argument("--schema", default="baseline/001_initial_schema", help="Schema name (relative to migrations/, without .sql)")
    parser.add_argument("--user", default="perftest", help="Database user")
    parser.add_argument("--dbname", default="perfdb", help="Database name")
    args = parser.parse_args()

    migration = ROOT / "migrations" / f"{args.schema}.sql"
    snapshot = migration.parent / "schema_v1.sql"

    if not migration.exists():
        print(f"Migration file not found: {migration}")
        sys.exit(1)

    apply_schema(migration, args.user, args.dbname)
    snapshot_schema(snapshot, args.user, args.dbname)
    print("\nDone.")
