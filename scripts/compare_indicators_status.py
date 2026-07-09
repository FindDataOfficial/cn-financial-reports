#!/usr/bin/env python3
"""Compare ``indicator_rules.json`` (the implemented rule set) against
``docs/indicators_status.csv`` (the per-company status report).

Produces two CSVs in ``docs/``:

* ``indicators_all_info.csv`` — every indicator from ``indicator_rules.json``
  with all of its fields flattened into columns (a superset of the status CSV).
* ``indicators_lost.csv`` — the comparison result: which indicators exist in
  only one of the two sources (the "lost" ones), plus field-level mismatches
  for indicators that exist in both.

Run::

    python scripts/compare_indicators_status.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "indicator_rules.json"
STATUS_PATH = ROOT / "docs" / "indicators_status.csv"
ALL_INFO_PATH = ROOT / "docs" / "indicators_all_info.csv"
LOST_PATH = ROOT / "docs" / "indicators_lost.csv"

# Company/report columns present in the status CSV (excluded from field compare).
STATUS_COMPANY_COLS = [
    "ICBC年报", "ICBC半年报", "ICBC_Q1", "ICBC_Q3",
    "茅台年报", "茅台半年报", "茅台Q1", "茅台Q3",
]


def format_applies_to(applies_to: dict) -> str:
    """Render applies_to the way the status CSV's 适用范围 column does."""
    industry = applies_to.get("industry", "*")
    sub_types = applies_to.get("sub_types", ["*"])
    companies = applies_to.get("companies", ["*"])
    companies_str = "[" + "/".join(companies) + "]"
    if industry == "*":
        return "universal" + companies_str
    sub_str = "/".join(sub_types) if sub_types else "*"
    return f"{industry}({sub_str}){companies_str}"


def resolve_extractor(rule: dict) -> str:
    """Resolve the extractor the way the status CSV's 提取器 column does.

    For report rules the real extractor lives in source.extractor; for the
    other source types it is the top-level extractor field.
    """
    st = rule.get("source_type")
    if st == "report":
        return rule.get("source", {}).get("extractor", "")
    if st == "akshare":
        return rule.get("extractor", "auto")
    if st == "computed":
        return "computed"
    if st == "external":
        return ""
    return rule.get("extractor", "")


def format_location(rule: dict) -> str:
    """Render the location the way the status CSV's 所在位置 column does."""
    st = rule.get("source_type")
    src = rule.get("source", {}) or {}
    if st == "akshare":
        return f"akshare:{src.get('statement', '')}"
    if st == "report":
        selectors = src.get("selectors", []) or []
        if selectors:
            return selectors[0].get("section", "")
        return ""
    if st == "computed":
        return f"computed:{src.get('formula', '')}"
    if st == "external":
        return "realtime/market"
    return ""


def join_list(values) -> str:
    if not values:
        return ""
    return " | ".join(str(v) for v in values)


def load_rules() -> list[dict]:
    with RULES_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["rules"]


def load_status() -> list[dict]:
    with STATUS_PATH.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_all_info(rules: list[dict]) -> None:
    """Dump every indicator with all fields flattened into a CSV."""
    fieldnames = [
        "指标名称", "别名", "模块", "子模块", "来源类型", "报表类型",
        "提取器", "适用范围", "所在位置",
        "适用行业", "适用子类型", "适用公司", "排除公司",
        "akshare_statement", "akshare_field",
        "report_selectors", "schema_hint",
        "computed_formula", "computed_inputs",
        "单位", "周期类型", "方向", "备注",
        "csv_annotated", "csv_source",
    ]
    with ALL_INFO_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rules:
            at = r.get("applies_to", {}) or {}
            src = r.get("source", {}) or {}
            selectors = src.get("selectors", []) or []
            row = {
                "指标名称": r.get("name", ""),
                "别名": join_list(r.get("aliases", [])),
                "模块": r.get("module", ""),
                "子模块": r.get("subgroup", ""),
                "来源类型": r.get("source_type", ""),
                "报表类型": r.get("report_type", ""),
                "提取器": resolve_extractor(r),
                "适用范围": format_applies_to(at),
                "所在位置": format_location(r),
                "适用行业": at.get("industry", ""),
                "适用子类型": join_list(at.get("sub_types", [])),
                "适用公司": join_list(at.get("companies", [])),
                "排除公司": join_list(at.get("exclude_companies", [])),
                "akshare_statement": src.get("statement", ""),
                "akshare_field": src.get("field", ""),
                "report_selectors": join_list(
                    [s.get("section", "") for s in selectors]
                ),
                "schema_hint": json.dumps(src.get("schema_hint"), ensure_ascii=False)
                if src.get("schema_hint") else "",
                "computed_formula": src.get("formula", ""),
                "computed_inputs": join_list(src.get("inputs", [])),
                "单位": r.get("unit", ""),
                "周期类型": r.get("period_type", ""),
                "方向": r.get("direction", ""),
                "备注": r.get("note", ""),
                "csv_annotated": r.get("_csv_annotated", ""),
                "csv_source": r.get("_csv_source", ""),
            }
            w.writerow(row)
    print(f"Wrote {ALL_INFO_PATH} ({len(rules)} indicators)")


def compare(rules: list[dict], status: list[dict]) -> None:
    rule_by_name = {r["name"]: r for r in rules}
    status_by_name = {r["指标名称"]: r for r in status}
    rule_names = set(rule_by_name)
    status_names = set(status_by_name)

    only_rules = sorted(rule_names - status_names)
    only_status = sorted(status_names - rule_names)
    shared = sorted(rule_names & status_names)

    # Field comparison for shared indicators.
    field_map = [
        ("模块", lambda r: r.get("module", "")),
        ("来源类型", lambda r: r.get("source_type", "")),
        ("报表类型", lambda r: r.get("report_type", "")),
        ("提取器", resolve_extractor),
        ("适用范围", lambda r: format_applies_to(r.get("applies_to", {}) or {})),
        ("所在位置", format_location),
    ]

    field_mismatch_counter = Counter()
    rows: list[dict] = []

    for name in only_rules:
        rows.append({
            "指标名称": name,
            "在规则中": "Y",
            "在状态CSV中": "N",
            "丢失方向": "lost_from_status",
            "字段差异": "",
            "判定": "LOST (in rules, missing from status CSV)",
        })
    for name in only_status:
        rows.append({
            "指标名称": name,
            "在规则中": "N",
            "在状态CSV中": "Y",
            "丢失方向": "lost_from_rules",
            "字段差异": "",
            "判定": "LOST (in status CSV, missing from rules)",
        })

    for name in shared:
        r = rule_by_name[name]
        s = status_by_name[name]
        diffs = []
        for col, getter in field_map:
            rule_val = getter(r)
            status_val = s.get(col, "")
            if rule_val != status_val:
                diffs.append(f"{col}: rules={rule_val!r} vs status={status_val!r}")
                field_mismatch_counter[col] += 1
        rows.append({
            "指标名称": name,
            "在规则中": "Y",
            "在状态CSV中": "Y",
            "丢失方向": "in_both",
            "字段差异": " ; ".join(diffs),
            "判定": "field_mismatch" if diffs else "matched",
        })

    with LOST_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["指标名称", "在规则中", "在状态CSV中", "丢失方向", "字段差异", "判定"],
        )
        w.writeheader()
        # Lost-first ordering: only_in_rules, only_in_status, then mismatches, then matched.
        order = {"lost_from_status": 0, "lost_from_rules": 1, "field_mismatch": 2, "in_both": 3}
        rows.sort(key=lambda x: (order.get(x["丢失方向"], 9), x["指标名称"]))
        for row in rows:
            w.writerow(row)

    n_mismatch = sum(1 for r in rows if r["判定"] == "field_mismatch")
    n_matched = sum(1 for r in rows if r["判定"] == "matched")
    print(f"Wrote {LOST_PATH}")
    print()
    print("================ SUMMARY ================")
    print(f"Indicators in rules:           {len(rules)}")
    print(f"Indicators in status CSV:      {len(status)}")
    print(f"Shared (in both):              {len(shared)}")
    print(f"LOST — in rules, not in status:    {len(only_rules)}")
    print(f"LOST — in status, not in rules:    {len(only_status)}")
    print(f"Shared & fully matched:        {n_matched}")
    print(f"Shared with field mismatch:    {n_mismatch}")
    if field_mismatch_counter:
        print("Field mismatch breakdown:")
        for col, cnt in field_mismatch_counter.most_common():
            print(f"  {col}: {cnt}")
    if only_rules:
        print("Indicators lost from status CSV:")
        for n in only_rules:
            print(f"  - {n}")
    if only_status:
        print("Indicators lost from rules:")
        for n in only_status:
            print(f"  - {n}")


def main() -> None:
    rules = load_rules()
    status = load_status()
    write_all_info(rules)
    compare(rules, status)


if __name__ == "__main__":
    main()
