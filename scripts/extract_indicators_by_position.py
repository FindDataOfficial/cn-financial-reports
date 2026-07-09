#!/usr/bin/env python3
"""Standalone position-CSV-driven indicator-extraction CLI for cnreport-mcp.

Runs the CSV-driven indicator rules engine from the command line (no MCP
server). Reuses ``indicators_client.extract_indicators_by_position`` +
``report_cache`` — no fetching/parsing/extraction logic is duplicated. The
position CSV (default ``docs/indicators_position.csv``) selects the indicator
set; realtime/external indicators are listed in ``skipped``.

Examples::

    python scripts/extract_indicators_by_position.py 601398 --year 2023
    python scripts/extract_indicators_by_position.py --from-file companies.txt --year 2023 \\
        --csv docs/indicators_position.csv --extractor python --out-dir ./out
    # --from-file runs companies concurrently (default batch cap 2); --concurrency
    # sets the in-call cap (default 4); --concurrency 1 forces sequential runs.
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

# Load .env so LLM_BASE_URL/LLM_API_KEY/LLM_MODEL are available to the engine.
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

import indicators_client  # noqa: E402

_CSV_COLS = ["indicator", "value", "unit", "source_type", "extractor", "period", "note", "status"]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extract the indicators named in a position CSV for a company/year."
    )
    p.add_argument("ticker_or_name", nargs="?",
                   help="6-digit ticker or company name (omit with --from-file)")
    p.add_argument("--from-file", help="Path to a file with one ticker/name per line")
    p.add_argument("--year", type=int, required=True, help="Fiscal year")
    p.add_argument("--csv", default="docs/indicators_position.csv",
                   help="Position CSV path (default: docs/indicators_position.csv)")
    p.add_argument("--extractor", choices=["auto", "llm", "python"], default="auto",
                   help="Extractor mode (default: auto). 'python' skips report rules whose extractor is LLM.")
    p.add_argument("--form", choices=["年度报告", "半年度报告", "第一季度报告", "第三季度报告"],
                   default="年度报告",
                   help="Periodic report form to extract from (default: 年度报告). "
                        "Indicators whose report_type doesn't include the form are skipped.")
    p.add_argument("--indicators", help="Comma-separated indicator names (subset; intersected with the CSV)")
    p.add_argument("--out-dir", default="./out", help="Output directory (default: ./out)")
    p.add_argument("--format", default="json,csv", help="Comma-separated output formats (default: json,csv)")
    p.add_argument("--concurrency", type=int, default=None,
                   help="In-call worker cap for one extraction (default: env EXTRACT_CONCURRENCY or 4). "
                        "Set to 1 for strictly sequential, reproducible extraction.")
    p.add_argument("--batch-concurrency", type=int, default=None,
                   help="Cross-company worker cap with --from-file (default: env EXTRACT_BATCH_CONCURRENCY or 2). "
                        "Peak in-flight LLM calls is bounded by batch × concurrency.")
    return p.parse_args(argv)


def _companies(args: argparse.Namespace) -> list[str]:
    if args.from_file:
        lines = Path(args.from_file).read_text(encoding="utf-8").splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if not args.ticker_or_name:
        raise SystemExit("error: provide a ticker/name, or use --from-file")
    return [args.ticker_or_name]


def _write_outputs(
    bundle: dict, stock: str, year: int, out_dir: Path, fmts: list[str], form: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Non-default form is appended to the stem so multi-form runs don't overwrite
    # each other (e.g. 601398_2023_第一季度报告.json vs 601398_2023.json).
    stem = f"{stock}_{year}" if form == "年度报告" else f"{stock}_{year}_{form}"
    if "json" in fmts:
        (out_dir / f"{stem}.json").write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if "csv" in fmts:
        _write_csv(bundle, out_dir / f"{stem}.csv")


def _write_csv(bundle: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(_CSV_COLS)
        for name, rec in (bundle.get("indicators") or {}).items():
            status = "ok" if rec.get("value") is not None else "unresolved"
            w.writerow([
                name,
                rec.get("value") if rec.get("value") is not None else "",
                rec.get("unit", ""),
                rec.get("source_type", ""),
                rec.get("extractor", ""),
                rec.get("period", ""),
                rec.get("note", ""),
                status,
            ])
        for s in bundle.get("skipped") or []:
            w.writerow([s.get("indicator"), "", "", s.get("source_type", ""), "", "",
                        s.get("note", "skipped"), "skipped"])
        for m in bundle.get("missing") or []:
            w.writerow([m.get("indicator"), "", "", "", "", "",
                        f"missing: {m.get('reason', '')}", "missing"])
        for u in bundle.get("unresolved") or []:
            w.writerow([u.get("indicator"), "", "", "", "", "",
                        u.get("note", "unresolved"), "unresolved"])


def _split_indicators(s: str | None) -> list[str] | None:
    if not s:
        return None
    return [x.strip() for x in s.split(",") if x.strip()]


def _extract_one(target: str, args: argparse.Namespace) -> dict:
    bundle = indicators_client.extract_indicators_by_position(
        target, args.year, csv_path=args.csv, extractor=args.extractor,
        indicators=_split_indicators(args.indicators), form=args.form,
        concurrency=args.concurrency,
    )
    # record provenance the engine doesn't own
    bundle["extractor_mode"] = args.extractor
    return bundle


def _emit(bundle: dict, target: str, args: argparse.Namespace, out_dir: Path, fmts: list[str]) -> None:
    """Write a successful bundle's outputs and print the OK summary line."""
    bundle["extractor_mode"] = args.extractor
    stock = bundle.get("stock_code") or target
    _write_outputs(bundle, stock, args.year, out_dir, fmts, args.form)
    n_ok = sum(1 for v in (bundle.get("indicators") or {}).values() if v.get("value") is not None)
    n_skip = len(bundle.get("skipped") or [])
    stem = f"{stock}_{args.year}" if args.form == "年度报告" else f"{stock}_{args.year}_{args.form}"
    print(
        f"[OK]   {stock} {args.year} {args.form}: {n_ok}/{len(bundle.get('indicators') or {})} indicators, "
        f"{n_skip} skipped (cached={bundle.get('cached')}) → {out_dir}/{stem}.{{json,csv}}"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    fmts = [f.strip() for f in args.format.split(",") if f.strip()]
    out_dir = Path(args.out_dir)
    failures: list[tuple[str, str]] = []

    companies = _companies(args)
    use_batch = bool(args.from_file) and len(companies) > 1

    if use_batch:
        # Many companies → run them concurrently via the batch entry point.
        targets = [(c, args.year, args.form) for c in companies]
        batch = indicators_client.extract_indicators_batch(
            targets, concurrency=args.batch_concurrency,
            extract_concurrency=args.concurrency,
            csv_path=args.csv, indicators=_split_indicators(args.indicators),
            form=args.form, extractor_mode=args.extractor,
        )
        for key, bundle in batch["results"].items():
            _emit(bundle, key, args, out_dir, fmts)
        for f in batch["failures"]:
            failures.append((f["target"], f["error"]))
            print(f"[FAIL] {f['target']} {args.year}: {f['error']}", file=sys.stderr)
    else:
        for target in companies:
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

            _emit(bundle, target, args, out_dir, fmts)

    if failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
