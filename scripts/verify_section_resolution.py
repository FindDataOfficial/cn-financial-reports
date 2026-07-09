#!/usr/bin/env python3
"""Verify section resolution improvement after python→llm migration."""
import json, sys, os, glob
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
import cnreport_tools as T
import report_section_map as RSM
import indicators_client as I

# Load ICBC report
cache_files = sorted(glob.glob(str(_ROOT / ".cache" / "reports" / "601398*.txt")))
if not cache_files:
    print("No cached ICBC report found")
    sys.exit(0)
txt_path = cache_files[0]
text = open(txt_path, encoding="utf-8", errors="replace").read()
outline_path = txt_path.replace(".txt", ".outline_enriched.json")
if os.path.exists(outline_path):
    outline = json.loads(open(outline_path, encoding="utf-8").read())
else:
    outline = T.parse_outline(text)

rules = json.loads((_ROOT / "indicator_rules.json").read_text(encoding="utf-8"))["rules"]
report_rules = [r for r in rules if r.get("source_type") == "report"]

# Check section resolution for all selectors
section_hits = Counter()
section_misses = Counter()
for r in report_rules:
    sels = (r.get("source") or {}).get("selectors", [])
    for s in sels:
        sec = s.get("section", "")
        body, matched = I._resolve_section(
            text, outline, r, "601398", form="年度报告",
        )
        if body:
            section_hits[sec] += 1
        else:
            section_misses[sec] += 1

print("Section resolution results (ICBC 2023 annual report):")
print(f"  Unique sections with hits:   {len(section_hits)}")
print(f"  Unique sections with misses: {len(section_misses)}")
print(f"  Total selector hits:   {sum(section_hits.values())}")
print(f"  Total selector misses: {sum(section_misses.values())}")
print()
if section_misses:
    print("Top 10 missed sections:")
    for sec, cnt in section_misses.most_common(10):
        print(f"  {cnt:3d}x  {sec}")
else:
    print("No missed sections!")
