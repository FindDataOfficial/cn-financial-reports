#!/usr/bin/env python3
"""Count indicators by extractor type and list LLM-extracted indicators."""
import json
from pathlib import Path

rules = json.loads(Path("indicator_rules.json").read_text(encoding="utf-8"))["rules"]

llm = [r for r in rules if r.get("source_type") == "report" and (
    r.get("extractor") == "llm" or (r.get("source") or {}).get("extractor") == "llm"
)]
py = [r for r in rules if r.get("source_type") == "report" and (
    (r.get("extractor") or "").startswith("python:")
)]
rt = [r for r in rules if r.get("source_type") == "report"]
ak = [r for r in rules if r.get("source_type") == "akshare"]
co = [r for r in rules if r.get("source_type") == "computed"]
ex = [r for r in rules if r.get("source_type") == "external"]

print(f"Total rules:       {len(rules)}")
print(f"  report (LLM):    {len(llm)}")
print(f"  report (python): {len(py)}")
print(f"  report total:    {len(rt)}")
print(f"  akshare:         {len(ak)}")
print(f"  computed:        {len(co)}")
print(f"  external:        {len(ex)}")
print()
print("LLM indicators:")
for r in sorted(llm, key=lambda x: x.get("module", "")):
    print(f"  [{r.get('module','')}] {r['name']}")
