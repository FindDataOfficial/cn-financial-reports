#!/usr/bin/env python3
"""Generate a CI-friendly support report for seed industry document types."""

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
    p = argparse.ArgumentParser(description="Generate support report for seed industry document types.")
    p.add_argument("--seed-file", default="docs/industry_seed_support.json", help="Path to seed document types json")
    p.add_argument("--baseline", default=str(C.default_baseline_path()), help="Path to industry baseline json")
    p.add_argument("--output", default="docs/industry_support_report.json", help="Output report path")
    return p.parse_args(argv)


def _load_seed_types(path: str | Path) -> list[str]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    vals = raw.get("document_types") if isinstance(raw, dict) else None
    if not isinstance(vals, list):
        raise ValueError("seed file must contain top-level document_types list")
    return [str(x).strip() for x in vals if str(x).strip()]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    doc_types = _load_seed_types(args.seed_file)
    items = []
    all_supported = True

    for dt in doc_types:
        rep = C.check_from_baselines(document_type=dt, baseline_path=args.baseline)
        if not rep.supported:
            all_supported = False
        items.append(
            {
                "document_type": dt,
                "declared_count": len(rep.declared),
                "llm_ready": rep.llm_ready,
                "script_ready": rep.script_ready,
                "supported": rep.supported,
                "missing_llm_rules": rep.missing_llm_rules,
                "missing_script_rules": rep.missing_script_rules,
            }
        )

    report = {
        "seed_count": len(doc_types),
        "all_supported": all_supported,
        "items": items,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all_supported else 2


if __name__ == "__main__":
    raise SystemExit(main())

