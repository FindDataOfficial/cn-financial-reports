#!/usr/bin/env python3
"""Debug LLM extraction: check section text, rule types, and try smaller sections."""
import json, os, sys, glob, time
from pathlib import Path
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
sys.path.insert(0, str(_ROOT))

import cnreport_tools as T
import indicators_client as I
import report_section_map as RSM

# Load cached ICBC ANNUAL report (not half-year)
cache_files = sorted(glob.glob(str(_ROOT / ".cache" / "reports" / "601398*年度报告*.txt")))
if not cache_files:
    cache_files = sorted(glob.glob(str(_ROOT / ".cache" / "reports" / "601398*.txt")))
txt_path = cache_files[0]
text = open(txt_path, encoding="utf-8", errors="replace").read()
outline_path = txt_path.replace(".txt", ".outline.json")
outline = json.loads(open(outline_path, encoding="utf-8").read())

print(f"Report: {Path(txt_path).name}")
print(f"Text: {len(text)} chars, Outline: {len(outline)} entries")
print()

# Check what rules exist as report-type
rules_data = json.loads((_ROOT / "indicator_rules.json").read_text(encoding="utf-8"))
all_rules = rules_data["rules"]

# Find report-type rules
test_names = ["资产总计", "负债合计", "营业收入", "利息收入", "每股收益", "资本充足率", "不良贷款率", "现金及存放中央银行款项"]
print("Rule types for test indicators:")
for name in test_names:
    for r in all_rules:
        if r["name"] == name:
            st = r.get("source_type", "?")
            ext = r.get("extractor", "?")
            mod = r.get("module", "?")
            print(f"  {name:30s}  source_type={st:10s}  extractor={ext:10s}  module={mod}")
            break
    else:
        print(f"  {name:30s}  NOT FOUND in rules")

print()

# Check outline entries containing '资产负债表'
print("Outline entries containing '资产负债表':")
for entry in outline:
    title = entry.get("title", "")
    if "资产负债表" in title:
        print(f"  ordinal={entry.get('ordinal','?'):4}  level={entry.get('level','?')}  title={title}")

print()

# Check what "资产负债表" resolves to for a balance_sheet rule
rule_bs = None
for r in all_rules:
    if r["name"] == "现金及存放中央银行款项" and r.get("source_type") == "report":
        rule_bs = r
        break

if rule_bs:
    body, matched = I._resolve_section(text, outline, rule_bs, "601398", form="年度报告")
    if body:
        print(f"Section '{matched}' resolved to {len(body)} chars")
        print("First 1000 chars:")
        print(body[:1000])
        print("...")
    else:
        print("Section not resolved")

print()

# Find actual balance sheet table in text
idx = text.find("合并及公司资产负债表")
if idx < 0:
    idx = text.find("合并资产负债表")
if idx >= 0:
    start = max(0, idx - 100)
    end = min(len(text), idx + 8000)
    bs_text = text[start:end]
    print(f"Found balance sheet at char {idx}, extracted {len(bs_text)} chars")
    print("First 500 chars:")
    print(bs_text[:500])

    # Test LLM with this smaller, targeted text
    print()
    print("--- Testing LLM extraction with targeted balance sheet text ---")
    # Find report-type rules for balance sheet items
    bs_rules = [r for r in all_rules if r.get("source_type") == "report"
                and r.get("module") == "balance_sheet"
                and r["name"] in ("现金及存放中央银行款项", "资产总计", "负债合计", "股东权益合计")]
    # Also try income statement
    is_rules = [r for r in all_rules if r.get("source_type") == "report"
                and r.get("module") == "income_statement"
                and r["name"] in ("利息收入", "营业收入")]

    if bs_rules:
        print(f"Testing {len(bs_rules)} balance_sheet rules with {len(bs_text)} chars")
        t0 = time.time()
        result = I._llm_extract_section(bs_text, bs_rules, "annual")
        elapsed = time.time() - t0
        print(f"LLM returned in {elapsed:.1f}s")
        for name, rec in result.items():
            val = rec.get("value")
            unit = rec.get("unit", "")
            note = rec.get("note", "")
            if val is not None:
                print(f"  {name:30s} = {val:>20} {unit:5s}  (note: {note})")
            else:
                print(f"  {name:30s} = {'NULL':>20}        (note: {note})")
    else:
        print("No balance_sheet report rules found")

    # Also test income statement
    is_idx = text.find("合并及公司利润表")
    if is_idx < 0:
        is_idx = text.find("合并利润表")
    if is_idx >= 0:
        is_start = max(0, is_idx - 100)
        is_end = min(len(text), is_idx + 5000)
        is_text = text[is_start:is_end]
        print(f"\nFound income statement at char {is_idx}, extracted {len(is_text)} chars")
        if is_rules:
            print(f"Testing {len(is_rules)} income_statement rules")
            t0 = time.time()
            result = I._llm_extract_section(is_text, is_rules, "annual")
            elapsed = time.time() - t0
            print(f"LLM returned in {elapsed:.1f}s")
            for name, rec in result.items():
                val = rec.get("value")
                unit = rec.get("unit", "")
                note = rec.get("note", "")
                if val is not None:
                    print(f"  {name:30s} = {val:>20} {unit:5s}  (note: {note})")
                else:
                    print(f"  {name:30s} = {'NULL':>20}        (note: {note})")
else:
    print("'合并资产负债表' not found in text")
    # Search for just "资产负债表"
    for i, line in enumerate(text.split("\n")[:200]):
        if "资产负债表" in line:
            print(f"  line {i}: {line[:100]}")
