#!/usr/bin/env python3
"""Migrate all python:* extractor rules to extractor: "llm" in indicator_rules.json.

Idempotent: re-running produces no diff when all rules already use "llm".
"""
import json
import sys
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parent.parent / "indicator_rules.json"

def migrate():
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rules = data.get("rules", [])
    changed = 0
    for r in rules:
        if r.get("source_type") != "report":
            continue
        ext = r.get("extractor", "")
        if ext.startswith("python:"):
            r["extractor"] = "llm"
            changed += 1
        # also fix nested source.extractor
        src = r.get("source") or {}
        if isinstance(src.get("extractor"), str) and src["extractor"].startswith("python:"):
            src["extractor"] = "llm"
    # write back with stable formatting
    RULES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Migrated {changed} rules from python:* to llm")
    return changed

if __name__ == "__main__":
    n = migrate()
    if n == 0:
        print("Already migrated — no changes needed (idempotent)")
