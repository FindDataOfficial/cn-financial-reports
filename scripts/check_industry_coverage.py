#!/usr/bin/env python3
"""Check LLM/script rule coverage for a document_type baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import industry_coverage as C  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check rule coverage for a document_type baseline.")
    p.add_argument("--baseline", default=str(C.default_baseline_path()), help="Path to industry_indicator_baseline.json")
    p.add_argument("--document-type", required=True, help="document_type to check (e.g. cn/bank/listed/annual-report)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rep = C.check_from_baselines(
        document_type=args.document_type,
        baseline_path=args.baseline,
    )

    if args.format == "json":
        print(
            json.dumps(
                {
                    "document_type": rep.document_type,
                    "declared": rep.declared,
                    "missing_llm_rules": rep.missing_llm_rules,
                    "missing_script_rules": rep.missing_script_rules,
                    "llm_ready": rep.llm_ready,
                    "script_ready": rep.script_ready,
                    "supported": rep.supported,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if rep.supported else 2

    print(f"document_type: {rep.document_type}")
    print(f"declared: {len(rep.declared)}")
    print(f"llm_ready: {rep.llm_ready} (missing={len(rep.missing_llm_rules)})")
    if rep.missing_llm_rules:
        for x in rep.missing_llm_rules:
            print(f"  - missing llm: {x}")
    print(f"script_ready: {rep.script_ready} (missing={len(rep.missing_script_rules)})")
    if rep.missing_script_rules:
        for x in rep.missing_script_rules:
            print(f"  - missing script: {x}")
    print(f"supported: {rep.supported}")
    return 0 if rep.supported else 2


if __name__ == "__main__":
    raise SystemExit(main())

