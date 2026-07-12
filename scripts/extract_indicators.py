#!/usr/bin/env python3
"""Standalone indicator-extraction CLI for fd-cn-report.

Runs the indicator rules engine from the command line (no MCP server). Reuses
`indicators_client` + `report_cache` — no fetching/parsing/extraction logic is
duplicated. Different companies can be processed against different rule files
via ``--rules`` (point at a different JSON per company batch).

Examples::

    python scripts/extract_indicators.py 601398 --year 2023
    python scripts/extract_indicators.py --from-file companies.txt --year 2023 \\
        --rules my_bank_rules.json --extractor python --out-dir ./out
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Make the repo root importable when run as a script from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import indicators_client  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract banking indicators for a company/year.")
    p.add_argument("ticker_or_name", nargs="?",
                   help="6-digit ticker or company name (omit with --from-file)")
    p.add_argument("--from-file", help="Path to a file with one ticker/name per line")
    p.add_argument("--year", type=int, required=True, help="Fiscal year")
    p.add_argument("--rules", help="Path to an indicator_rules.json to use instead of the default")
    p.add_argument("--extractor", choices=["auto", "llm", "python"], default="auto",
                   help="Extractor mode (default: auto). 'python' skips report rules whose extractor is LLM.")
    p.add_argument("--indicators", help="Comma-separated indicator names to extract (default: all applicable)")
    p.add_argument("--out-dir", default="./out", help="Output directory (default: ./out)")
    p.add_argument("--format", default="json,csv", help="Comma-separated output formats (default: json,csv)")
    return p.parse_args(argv)


def _companies(args: argparse.Namespace) -> list[str]:
    if args.from_file:
        lines = Path(args.from_file).read_text(encoding="utf-8").splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if not args.ticker_or_name:
        raise SystemExit("error: provide a ticker/name, or use --from-file")
    return [args.ticker_or_name]


def _write_outputs(bundle: dict, stock: str, year: int, out_dir: Path, fmts: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{stock}_{year}"
    if "json" in fmts:
        (out_dir / f"{stem}.json").write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if "csv" in fmts:
        _write_csv(bundle, out_dir / f"{stem}.csv")


def _write_csv(bundle: dict, path: Path) -> None:
    cols = ["indicator", "value", "unit", "source_type", "extractor", "period", "note"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for name, rec in (bundle.get("indicators") or {}).items():
            w.writerow([
                name,
                rec.get("value") if rec.get("value") is not None else "",
                rec.get("unit", ""),
                rec.get("source_type", ""),
                rec.get("extractor", ""),
                rec.get("period", ""),
                rec.get("note", ""),
            ])
        for m in bundle.get("missing") or []:
            w.writerow([m.get("indicator"), "", "", "", "", "", f"missing: {m.get('reason','')}"])
        for u in bundle.get("unresolved") or []:
            w.writerow([u.get("indicator"), "", "", "", "", "", u.get("note", "unresolved")])


def _extract_one(target: str, args: argparse.Namespace) -> dict:
    indicators = None
    if args.indicators:
        indicators = [s.strip() for s in args.indicators.split(",") if s.strip()]
    bundle = indicators_client.extract_indicators(
        target, args.year, indicators=indicators, extractor_mode=args.extractor,
    )
    # record provenance the engine doesn't own
    bundle["rule_file"] = str(indicators_client._REGISTRY_PATH)
    bundle["extractor_mode"] = args.extractor
    return bundle


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.rules:
        indicators_client.set_registry_path(args.rules)

    fmts = [f.strip() for f in args.format.split(",") if f.strip()]
    out_dir = Path(args.out_dir)
    failures: list[tuple[str, str]] = []

    for target in _companies(args):
        try:
            bundle = _extract_one(target, args)
        except Exception as e:  # noqa: BLE001 — CLI boundary: keep going across companies
            failures.append((target, f"{type(e).__name__}: {e}"))
            print(f"[FAIL] {target} {args.year}: {type(e).__name__}: {e}", file=sys.stderr)
            continue

        if "error" in bundle:
            failures.append((target, bundle["error"]))
            print(f"[FAIL] {target} {args.year}: {bundle['error']}", file=sys.stderr)
            continue

        stock = bundle.get("stock_code") or target
        _write_outputs(bundle, stock, args.year, out_dir, fmts)
        n_ok = sum(1 for v in (bundle.get("indicators") or {}).values() if v.get("value") is not None)
        print(
            f"[OK]   {stock} {args.year}: {n_ok}/{len(bundle.get('indicators') or {})} indicators "
            f"(cached={bundle.get('cached')}) → {out_dir}/{stock}_{args.year}.{{json,csv}}"
        )

    if failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
