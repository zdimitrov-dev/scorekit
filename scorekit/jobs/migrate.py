"""Apply the SQL files in ``db/migrations`` in name order.

Deliberately minimal: every migration is written to be **idempotent**, so re-running the
whole directory is safe and no applied-migrations ledger is needed. That trade buys a lot
of simplicity at this size; if migrations ever stop being cheap to re-run, this is the
thing to replace.

Goes through a direct Postgres connection because DDL cannot be issued over PostgREST,
which is what the rest of the codebase uses.

    python -m scorekit.jobs.migrate
    python -m scorekit.jobs.migrate --dry-run
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import psycopg2

from ..config import settings

log = logging.getLogger("scorekit.migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


def apply_migrations(dry_run: bool = False) -> int:
    if not settings.supabase_db_url:
        raise SystemExit("SUPABASE_DB_URL must be set to run migrations (see .env.example).")

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        log.info("no migrations found in %s", MIGRATIONS_DIR)
        return 0

    if dry_run:
        for path in files:
            log.info("[dry-run] would apply %s", path.name)
        return len(files)

    conn = psycopg2.connect(settings.supabase_db_url)
    try:
        # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on Postgres.
        conn.autocommit = True
        with conn.cursor() as cur:
            for path in files:
                log.info("applying %s", path.name)
                cur.execute(path.read_text(encoding="utf-8"))
    finally:
        conn.close()
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply db/migrations/*.sql (idempotent).")
    parser.add_argument("--dry-run", action="store_true", help="list migrations, apply none")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    n = apply_migrations(dry_run=args.dry_run)
    log.info("%s%d migration(s)", "[dry-run] " if args.dry_run else "applied ", n)


if __name__ == "__main__":
    main()
