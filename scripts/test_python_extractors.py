#!/usr/bin/env python3
"""Test Python extractors against real report section text.

Loads the cached ICBC (601398) 2023 annual report, resolves sections for
each python-extractor rule, runs the extractor, and prints a summary of
hits vs misses with the actual extracted values.
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import cnreport_tools as T
import indicators_client as I
import indicators_extractors as IE
import report_section_map as RSM

# ── load the cached ICBC report ──
_CACHE_STEM = "601398_2023_年度报告_1219429144"
_REPORT_TXT = _ROOT / ".cache" / "reports" / f"{_CACHE_STEM}.txt"
_REPORT_OUTLINE = _ROOT / ".cache" / "reports" / f"{_CACHE_STEM}.outline_enriched.json"

if not _REPORT_TXT.exists():
    # try finding any cached ICBC report
    cache_dir = _ROOT / ".cache" / "reports"
    txts = sorted(cache_dir.glob("601398*.txt"))
    if txts:
        _REPORT_TXT = txts[0]
        _REPORT_OUTLINE = _REPORT_TXT.with_suffix(".outline_enriched.json")
    else:
        print("ERROR: no cached ICBC report found in .cache/reports/")
        sys.exit(1)

print(f"Report: {_REPORT_TXT.name}")
text = _REPORT_TXT.read_text(encoding="utf-8", errors="replace")
if _REPORT_OUTLINE.exists():
    outline = json.loads(_REPORT_OUTLINE.read_text(encoding="utf-8"))
else:
    outline = T.parse_outline(text)
page_offsets_path = _REPORT_TXT.with_suffix("")
# try page offsets
po_path = _ROOT / ".cache" / "reports" / f"{_CACHE_STEM}.page_offsets.json"
page_offsets = []
if po_path.exists():
    page_offsets = json.loads(po_path.read_text(encoding="utf-8"))
page_count = len(page_offsets) - 1 if len(page_offsets) > 1 else 0

print(f"Text length: {len(text)} chars, outline entries: {len(outline)}")

# ── load rules and filter to python-extractor report rules ──
rules_data = json.loads((_ROOT / "indicator_rules.json").read_text(encoding="utf-8"))
all_rules = rules_data["rules"]

py_rules = [
    r for r in all_rules
    if r.get("source_type") == "report"
    and (r.get("extractor") or "").startswith("python:")
]
print(f"\nPython-extractor report rules: {len(py_rules)}")

# ── group by extractor name ──
from collections import Counter
ext_counts = Counter(r.get("extractor", "") for r in py_rules)
print("By extractor:")
for ext, cnt in sorted(ext_counts.items()):
    print(f"  {ext}: {cnt}")

# ── test each rule ──
hits = 0
misses = 0
errors = 0
results = []

for rule in sorted(py_rules, key=lambda x: (x.get("extractor", ""), x.get("module", ""), x["name"])):
    ext_name = rule.get("extractor", "")
    fn = IE.get(ext_name.split(":", 1)[1]) if ":" in ext_name else None
    if fn is None:
        results.append((rule, "NO_EXTRACTOR", None, f"extractor {ext_name} not registered"))
        errors += 1
        continue

    # resolve section text
    section_text, matched = I._resolve_section(
        text, outline, rule, "601398",
        form="年度报告",
        page_offsets=page_offsets or None,
        page_count=page_count,
    )
    if section_text is None:
        results.append((rule, "SECTION_NOT_FOUND", None, f"tried: {matched[:3]}..."))
        misses += 1
        continue

    # run the extractor
    try:
        res = fn(section_text, rule, "annual")
        val = res.get("value")
        if val is not None:
            results.append((rule, "OK", val, res.get("note", "")))
            hits += 1
        else:
            results.append((rule, "EXTRACTOR_NULL", None, res.get("note", "")))
            misses += 1
    except Exception as e:
        results.append((rule, "ERROR", None, f"{type(e).__name__}: {e}"))
        errors += 1

# ── summary ──
print(f"\n{'='*80}")
print(f"RESULTS: {hits} hits, {misses} misses, {errors} errors  (total {len(py_rules)})")
print(f"{'='*80}")

# group by extractor
for ext_name in sorted(ext_counts):
    ext_results = [(r, s, v, n) for r, s, v, n in results if r.get("extractor") == ext_name]
    ext_hits = sum(1 for _, s, _, _ in ext_results if s == "OK")
    ext_misses = sum(1 for _, s, _, _ in ext_results if s != "OK")
    print(f"\n--- {ext_name} ({ext_hits}/{len(ext_results)} hit) ---")
    for rule, status, val, note in ext_results:
        val_str = f"{val:>20}" if val is not None else f"{'—':>20}"
        sels = " / ".join(s.get("section", "") for s in (rule.get("source") or {}).get("selectors", []))
        print(f"  {status:20s} {val_str}  {rule['name']:40s}  sel=[{sels}]  note={note}")

# also check what the out/ bundle says
out_path = _ROOT / "out" / "601398_2023.json"
if out_path.exists():
    out_bundle = json.loads(out_path.read_text(encoding="utf-8"))
    out_indicators = out_bundle.get("indicators", {})
    print(f"\n{'='*80}")
    print("Comparing with out/601398_2023.json baseline:")
    print(f"{'='*80}")
    baseline_hits = 0
    baseline_nulls = 0
    for rule, status, val, note in results:
        name = rule["name"]
        out_val = out_indicators.get(name, {}).get("value")
        if out_val is not None:
            baseline_hits += 1
        else:
            baseline_nulls += 1
    print(f"  Baseline: {baseline_hits} with values, {baseline_nulls} null")
    print(f"  Now:      {hits} with values, {misses + errors} null/miss")
