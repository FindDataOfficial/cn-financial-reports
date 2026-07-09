#!/usr/bin/env python3
"""One-shot migration: seed ``llm_rules`` from ``indicator_rules.json``.

Idempotent — re-running over an unchanged JSON inserts 0 rows and updates 0
rows (change-detected per column). ``script_rules`` is untouched (no script
rules exist in the JSON; they are produced by the generator skills).

Honors ``DAAS_DATABASE_URL`` (default ``sqlite:///daas.db``).

Usage::

    python scripts/migrate_rules_to_db.py
    python scripts/migrate_rules_to_db.py --rules path/to/indicator_rules.json
    DAAS_DATABASE_URL=sqlite:///tmp/test.db python scripts/migrate_rules_to_db.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# allow running as `python scripts/migrate_rules_to_db.py` from the repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import rules_db  # noqa: E402


def migrate(rules_path: str | Path | None = None, db_url: str | None = None) -> dict:
    """Seed ``llm_rules`` from a JSON rule file (idempotent)."""
    path = Path(rules_path) if rules_path else rules_db.DEFAULT_RULES_JSON
    return rules_db.migrate_from_json(path, db_url=db_url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rules",
        default=None,
        help="Path to an indicator_rules.json to migrate (default: the repo's).",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Override DAAS_DATABASE_URL for this run (e.g. sqlite:///tmp/x.db).",
    )
    args = parser.parse_args(argv)

    summary = migrate(args.rules, args.db_url)
    print(
        "rules migration: "
        f"inserted={summary['inserted']} "
        f"updated={summary['updated']} "
        f"unchanged={summary['unchanged']} "
        f"total={summary['total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
