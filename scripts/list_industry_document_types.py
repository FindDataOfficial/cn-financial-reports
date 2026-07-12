#!/usr/bin/env python3
"""List candidate document_type values per industry.

Examples::

  python scripts/list_industry_document_types.py
  python scripts/list_industry_document_types.py --industry bank
  python scripts/list_industry_document_types.py --taxonomy docs/industry_taxonomy.json --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import industry_taxonomy as IT  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="List industry document_type values.")
    p.add_argument("--taxonomy", default=str(IT.default_taxonomy_path()), help="Path to industry_taxonomy.json")
    p.add_argument("--industry", help="Filter to one Shenwan L1 index code (e.g. 801780)")
    p.add_argument("--country", help="Country code: cn or hk (default: both)")
    p.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    tax = IT.load_taxonomy(args.taxonomy)
    entries = IT.list_document_types(tax, industry=args.industry, country=args.country)

    if args.format == "json":
        payload = [
            {
                "industry": e.industry,
                "company_type": e.company_type,
                "report_kind": e.report_kind,
                "document_type": e.document_type,
                "label": e.label,
            }
            for e in entries
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for e in entries:
        label = f" ({e.label})" if e.label else ""
        print(f"{e.document_type}{label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

