"""Fetch a bank annual report, parse its 目录, and map every report-type
indicator rule's selectors[] against the real TOC. Prints the full outline
plus a per-rule resolution report."""
from __future__ import annotations
import sys, time
sys.path.insert(0, ".")
import cninfo_client, report_cache, cnreport_tools as T, indicators_client as I

TARGET = "601398"
YEAR = 2023
FORM = "年度报告"

def main():
    co = cninfo_client.lookup_company(TARGET)
    assert co, "company not found"
    filings = cninfo_client.query_announcements(co["stock_code"], co["org_id"],
                                                form=FORM, year=YEAR, limit=5)
    assert filings, "no filing"
    top = filings[0]
    pdf = top["pdf_url"]
    print(f"company={co['name']} stock={co['stock_code']} year={YEAR}")
    print(f"filing: {top['title']}")
    print(f"pdf: {pdf}")
    print("fetching + parsing (cache-backed)…")
    t0 = time.time()
    text, info = report_cache.get_or_fetch(
        pdf, stock_code=co["stock_code"], year=YEAR, form=FORM,
        announcement_id=top.get("announcement_id") or "")
    print(f"  fetched in {time.time()-t0:.1f}s  cached={info['cached']}  chars={len(text)}")
    outline = T.parse_outline(text)
    print(f"  outline entries: {len(outline)}")
    print()

    # save the outline for reference
    import json
    from pathlib import Path
    out = Path("docs/icbc_2023_outline.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved outline → {out}")
    print()

    # print the full TOC
    print("=" * 70)
    print("目录 (Table of Contents)")
    print("=" * 70)
    for e in outline:
        indent = "  " * (e["level"] - 1)
        print(f"{e['ordinal']:>3} {indent}{e['title']}")
    print()

    # map report-type rules
    print("=" * 70)
    print("Indicator → section resolution (report-type rules)")
    print("=" * 70)
    rules = [r for r in I._rules() if r["source_type"] == "report"]
    hits, misses = [], []
    for r in rules:
        body, matched = I._resolve_section(text, outline, r, co["stock_code"])
        status = "HIT " if body else "MISS"
        line = f"[{status}] {r['name']}"
        if body:
            line += f"  →  section matched: {matched!r}"
            hits.append((r["name"], matched, len(body)))
        else:
            line += f"  →  tried {matched}"
            misses.append((r["name"], matched))
        print(line)

    print()
    print(f"HITS: {len(hits)}  MISSES: {len(misses)}")
    if misses:
        print("\nMisses (selectors that did not match this TOC):")
        for name, tried in misses:
            print(f"  - {name}: tried {tried}")

if __name__ == "__main__":
    main()
