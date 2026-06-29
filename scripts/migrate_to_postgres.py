"""Migrate the local file history store → Postgres (the Oracle-VM deploy).

The local `runs/cache/` + `runs/chat/` store (seeded by `backfill_history.py` and enriched by
`recover_transcripts.py`) is the single source of truth. This copies every run into the
`history_runs` Postgres table so the deploy serves durable history with NO Logfire dependency.

On the VM: set `DATABASE_URL=postgresql://…` in `.env`, copy the `runs/` directory across (or run
this from a checkout that has it), then:

    DATABASE_URL=postgresql://user:pass@host:5432/db  uv run python scripts/migrate_to_postgres.py

Idempotent: re-running upserts by run_id. Reads files regardless of DATABASE_URL; writes to Postgres
(refuses to run if DATABASE_URL is unset, since the source and destination would then be identical).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from gambit import history  # noqa: E402
from gambit.settings import settings  # noqa: E402


def main() -> None:
    if not settings.database_url:
        print("DATABASE_URL is not set — nothing to migrate INTO. Set it to your Oracle Postgres DSN.")
        return

    source = history.FileHistory()                       # always read from the local files
    details = history.export_all(source)
    if not details:
        print("Local store is empty (run backfill_history.py / recover_transcripts.py first).")
        return

    try:
        dest = history.PostgresHistory(settings.database_url)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not connect to Postgres: {exc}")
        return

    pairs = [(history.summarize(rid, d), d) for rid, d in details.items()]
    dest.bulk_replace(pairs)

    with_moves = sum(1 for _s, d in pairs if d.get("moves"))
    print(f"Migrated {len(pairs)} runs → Postgres history_runs ({with_moves} with transcripts).")
    print(f"  destination rows now: {len(dest.list_runs())}")


if __name__ == "__main__":
    main()
