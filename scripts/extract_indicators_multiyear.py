#!/usr/bin/env python3
"""Extract a company's latest N years of banking indicators WITHOUT LLM.

Uses ``indicators_client.extract_indicators`` with ``extractor_mode="python"``
so every rule whose extractor is LLM is skipped (reported as unresolved rather
than calling an LLM). Writes ONE combined wide CSV: one row per indicator,
one column per year.

Example::

    python scripts/extract_indicators_multiyear.py 000001 --years 5 \
        --out ./out/000001_indicators_5y.csv

Years are independent (each fetches its own PDF) and run concurrently up to
``--batch-concurrency`` (default 2); ``--concurrency`` sets the in-call cap.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import indicators_client  # noqa: E402
import cnreport_tools as T  # noqa: E402


def _latest_years(target: str, n: int) -> list[int]:
    """Return the N most recent fiscal years that have an annual report."""
    filings = T.list_filings(target, form="年度报告")
    years: set[int] = set()
    for f in filings or []:
        title = (f.get("title") or "")
        if "摘要" in title or "半年报" in title or "季报" in title:
            continue
        for tok in title.replace("年", " ").split():
            tok = tok.strip()
            if tok.isdigit() and 1990 <= int(tok) <= 2100:
                years.add(int(tok))
    years = sorted(years, reverse=True)
    if not years:
        raise SystemExit(f"error: no annual filings found for {target}")
    chosen = years[:n]
    print(f"[info] {target}: latest {n} years with annual reports → {chosen}")
    return chosen


def write_combined_csv(bundles: dict[int, dict], target: str, path: Path) -> None:
    """Wide CSV: indicator | unit | source_type | extractor | <year...> | notes.

    Year cells hold the numeric value (or empty when not resolved). The trailing
    ``notes`` column lists, per failed year, a short reason — so a missing value
    is attributed to the specific year it failed for, not leaked onto the row.
    """
    # collect the union of indicator names across years (preserve first-seen order)
    names: list[str] = []
    seen: set[str] = set()
    for year in sorted(bundles):
        for nm, rec in (bundles[year].get("indicators") or {}).items():
            if nm not in seen:
                seen.add(nm)
                names.append(nm)
        for m in bundles[year].get("missing") or []:
            if m.get("indicator") not in seen:
                seen.add(m.get("indicator"))
                names.append(m.get("indicator"))
        for u in bundles[year].get("unresolved") or []:
            if u.get("indicator") not in seen:
                seen.add(u.get("indicator"))
                names.append(u.get("indicator"))

    years = sorted(bundles)
    header = ["indicator", "unit", "source_type", "extractor", *map(str, years), "notes"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for nm in names:
            unit = src = ext = ""
            cells: list[str] = []
            notes: list[str] = []
            for year in years:
                b = bundles[year]
                rec = (b.get("indicators") or {}).get(nm)
                if rec is not None:
                    if not unit:
                        unit = rec.get("unit", "") or ""
                    if not src:
                        src = rec.get("source_type", "") or ""
                    if not ext:
                        ext = rec.get("extractor", "") or ""
                    v = rec.get("value")
                    if v is not None:
                        cells.append(f"{v:g}" if isinstance(v, float) else str(v))
                    else:
                        cells.append("")
                        notes.append(f"{year}: {rec.get('note') or 'unresolved'}")
                    continue
                # not in indicators → check missing / unresolved
                tag = ""
                for m in b.get("missing") or []:
                    if m.get("indicator") == nm:
                        tag = f"missing: {m.get('reason', '')}"
                        break
                if not tag:
                    for u in b.get("unresolved") or []:
                        if u.get("indicator") == nm:
                            tag = u.get("note", "unresolved") or "unresolved"
                            break
                cells.append("")
                notes.append(f"{year}: {tag or 'missing'}")
            w.writerow([nm, unit, src, ext, *cells, "; ".join(notes)])
    print(f"[ok] wrote {len(names)} indicators × {len(years)} years → {path}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Extract N latest years of indicators (no LLM) into one CSV.")
    p.add_argument("ticker_or_name", help="6-digit ticker or company name")
    p.add_argument("--years", type=int, default=5, help="Number of latest years (default 5)")
    p.add_argument("--out", default="./out/{ticker}_indicators_{n}y.csv",
                   help="Output CSV path. Use {ticker} and {n} placeholders.")
    p.add_argument("--extractor", choices=["python"], default="python",
                   help="Fixed to 'python' (no LLM).")
    p.add_argument("--concurrency", type=int, default=None,
                   help="In-call worker cap for one extraction (default: env EXTRACT_CONCURRENCY or 4).")
    p.add_argument("--batch-concurrency", type=int, default=None,
                   help="Cross-year worker cap (default: env EXTRACT_BATCH_CONCURRENCY or 2). "
                        "Years are independent (own PDF each), so this is the dominant speedup.")
    args = p.parse_args(argv)

    years = _latest_years(args.ticker_or_name, args.years)
    print(f"[run] {args.ticker_or_name}: {len(years)} years (extractor={args.extractor}) ...")
    targets = [(args.ticker_or_name, y) for y in years]
    # Years are independent (each fetches its own PDF) → run concurrently via the
    # batch entry point with csv_path=None so each target uses extract_indicators
    # directly (python-only, no LLM) rather than the position path.
    batch = indicators_client.extract_indicators_batch(
        targets, concurrency=args.batch_concurrency,
        extract_concurrency=args.concurrency,
        csv_path=None, form="年度报告", extractor_mode="python",
    )

    bundles: dict[int, dict] = {}
    for year in years:
        key = f"{args.ticker_or_name}_{year}"
        bundle = batch["results"].get(key)
        if bundle is None:
            failure = next((fl for fl in batch["failures"] if fl["target"] == key), None)
            msg = failure["error"] if failure else "missing"
            print(f"[FAIL] {args.ticker_or_name} {year}: {msg}", file=sys.stderr)
            continue
        if "error" in bundle:
            print(f"[FAIL] {args.ticker_or_name} {year}: {bundle['error']}", file=sys.stderr)
            continue
        n_ok = sum(1 for v in (bundle.get("indicators") or {}).values() if v.get("value") is not None)
        n_tot = len(bundle.get("indicators") or {})
        print(f"[ok]  {args.ticker_or_name} {year}: {n_ok}/{n_tot} resolved "
              f"(cached={bundle.get('cached')})")
        bundles[year] = bundle

    if not bundles:
        print("error: no years extracted successfully", file=sys.stderr)
        return 1

    out = Path(args.out.format(ticker=args.ticker_or_name, n=len(bundles)))
    write_combined_csv(bundles, args.ticker_or_name, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
