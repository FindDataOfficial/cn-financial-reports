#!/usr/bin/env python3
"""CLI: migrate docs/indicators_position.csv into indicator_rules.json.

Idempotent — re-running over an unchanged CSV is a no-op (use ``--check`` to
verify). CSV-only indicators are appended as new rules; overlapping indicators
annotate the existing hand-authored rules (preserving their selectors/applies_to);
hand-authored rules are never dropped.

Examples::

    python scripts/migrate_indicators_csv.py
    python scripts/migrate_indicators_csv.py --check
    python scripts/migrate_indicators_csv.py --csv docs/my_positions.csv --rules my_rules.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import indicators_csv_migration as mig  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Migrate the position CSV into the indicator rule set.")
    p.add_argument("--csv", default=str(mig._DEFAULT_CSV), help="Position CSV path")
    p.add_argument("--rules", default=str(mig._DEFAULT_RULES), help="indicator_rules.json path")
    p.add_argument("--check", action="store_true",
                   help="Dry-run: report whether indicator_rules.json would change")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    summary = mig.migrate(args.csv, args.rules, dry_run=args.check)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.check:
        if summary["changed_file"]:
            print("→ indicator_rules.json is out of date with the CSV (run without --check to apply)")
            return 1
        print("✓ indicator_rules.json is up to date with the CSV")
        return 0
    print(f"✓ migrated → {summary.get('rules_path')}: "
          f"{summary['total']} rules ({summary['hand_authored']} hand-authored, "
          f"{summary['csv_sourced']} csv-sourced, {summary['annotated']} annotated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
