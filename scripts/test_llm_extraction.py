#!/usr/bin/env python3
"""Test real LLM extraction against a cached annual report.

Loads the ICBC 2023 annual report from cache, resolves sections, and
calls the LLM to extract a subset of indicators. Prints the results.
"""
import json
import os
import sys
import glob
import time
from pathlib import Path
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
sys.path.insert(0, str(_ROOT))

import cnreport_tools as T
import indicators_client as I
import report_section_map as RSM

# Verify LLM config
cfg = T.llm_config()
print(f"LLM config: model={cfg['model']}, base_url={cfg['base_url'][:30]}..., key={'set' if cfg['api_key'] else 'NOT SET'}")
if not cfg["api_key"]:
    print("ERROR: LLM_API_KEY not set")
    sys.exit(1)

# Load cached ICBC report
cache_files = sorted(glob.glob(str(_ROOT / ".cache" / "reports" / "601398*.txt")))
if not cache_files:
    print("No cached ICBC report found")
    sys.exit(1)

txt_path = cache_files[0]
text = open(txt_path, encoding="utf-8", errors="replace").read()
outline_path = txt_path.replace(".txt", ".outline_enriched.json")
if os.path.exists(outline_path):
    outline = json.loads(open(outline_path, encoding="utf-8").read())
else:
    outline = T.parse_outline(text)

print(f"Report: {Path(txt_path).name} ({len(text)} chars, {len(outline)} outline entries)")
print()

# Pick a test set: a few balance_sheet items + a few report_section items
# that should be findable in the ICBC annual report
test_indicators = [
    # balance_sheet items (should resolve to 合并资产负债表)
    "资产总计",
    "负债合计",
    "股东权益合计",
    "现金及存放中央银行款项",
    # income_statement items
    "营业收入",
    "利息收入",
    # report_section items
    "每股收益",
    "不良贷款率",
    "资本充足率",
]

print(f"Testing {len(test_indicators)} indicators via real LLM extraction...")
print(f"{'='*80}")

# Load rules
rules_data = json.loads((_ROOT / "indicator_rules.json").read_text(encoding="utf-8"))
all_rules = rules_data["rules"]

# Filter to just our test indicators
test_rules = []
for name in test_indicators:
    for r in all_rules:
        if r["name"] == name and r.get("source_type") == "report":
            test_rules.append(r)
            break

print(f"Found {len(test_rules)} matching report rules")
for r in test_rules:
    sels = (r.get("source") or {}).get("selectors", [])
    print(f"  [{r.get('module','')}] {r['name']:30s}  sels={[s.get('section','') for s in sels]}")
print()

# Resolve sections for each rule
section_map: dict[str, list] = {}  # section_key -> [rules]
for r in test_rules:
    body, matched = I._resolve_section(text, outline, r, "601398", form="年度报告")
    if body:
        section_key = matched
        if section_key not in section_map:
            section_map[section_key] = []
        section_map[section_key].append((r, body))
        print(f"  RESOLVED  {r['name']:30s} -> section='{section_key}' ({len(body)} chars)")
    else:
        print(f"  MISSED    {r['name']:30s} -> section not found")

print(f"\n{len(section_map)} unique sections resolved")
print()

# Run LLM extraction per section×module
all_results = {}
for section_key, rules_with_body in section_map.items():
    # Group by module
    by_module: dict[str, list] = {}
    for r, body in rules_with_body:
        mod = r.get("module", "report_section")
        if mod not in by_module:
            by_module[mod] = []
        by_module[mod].append((r, body))

    for mod, items in by_module.items():
        rules = [r for r, _ in items]
        body = items[0][1]  # same section text
        print(f"LLM call: section='{section_key}', module='{mod}', {len(rules)} indicators")
        print(f"  indicators: {[r['name'] for r in rules]}")

        try:
            t0 = time.time()
            result = I._llm_extract_section(body, rules, "annual")
            elapsed = time.time() - t0
            print(f"  LLM returned in {elapsed:.1f}s")
            for r in rules:
                rec = result.get(r["name"], {"value": None, "note": "not returned"})
                val = rec.get("value")
                unit = rec.get("unit", r.get("unit", ""))
                note = rec.get("note", "")
                all_results[r["name"]] = (val, unit, note)
                if val is not None:
                    print(f"    {r['name']:30s} = {val:>20} {unit:5s}  (note: {note})")
                else:
                    print(f"    {r['name']:30s} = {'NULL':>20}        (note: {note})")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            for r in rules:
                all_results[r["name"]] = (None, "", f"error: {e}")

        print()

# Summary
print(f"{'='*80}")
print("SUMMARY:")
hits = sum(1 for v, _, _ in all_results.values() if v is not None)
misses = sum(1 for v, _, _ in all_results.values() if v is None)
print(f"  Hits:   {hits}")
print(f"  Misses: {misses}")
print(f"  Total:  {len(all_results)}")
print()
for name in test_indicators:
    if name in all_results:
        val, unit, note = all_results[name]
        if val is not None:
            print(f"  {name:30s} = {val} {unit}")
        else:
            print(f"  {name:30s} = NULL  ({note})")
    else:
        print(f"  {name:30s} = SECTION NOT FOUND")
