#!/usr/bin/env python3
"""Locate every fetchable indicator inside an example annual report and write
the positions to a CSV.

The example report is 工商银行 2023 年度报告 (cached locally, no network).
For each ``fetchable=yes`` row in ``docs/indicators-coverage.csv`` we look up its
rule in ``indicator_rules.json`` and resolve the rule against the report's 目录:

  * ``report`` rules  → the matched TOC section (title / ordinal / level /
    char offsets / sliced body length), plus the selector chain that hit.
  * ``akshare`` rules → the akshare ``statement.field`` plus the report's
    resolved-statement TOC entry as a hint.
  * ``computed`` rules → the formula and its inputs (no report position).

Output: ``docs/icbc_2023_indicator_positions.csv``.

Reuses ``cnreport_tools`` + ``indicators_client._resolve_section`` so the
resolution is identical to what the extraction engine uses at runtime.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import cnreport_tools as T  # noqa: E402
import indicators_client as I  # noqa: E402

STOCK_CODE = "601398"
YEAR = 2023
CACHE_STEM = f"{STOCK_CODE}_{YEAR}_年度报告_1219429144"
REPORT_TXT = _REPO_ROOT / ".cache" / "reports" / f"{CACHE_STEM}.txt"
COVERAGE_CSV = _REPO_ROOT / "docs" / "indicators-coverage.csv"
RULES_JSON = _REPO_ROOT / "indicator_rules.json"
OUT_CSV = _REPO_ROOT / "docs" / "icbc_2023_indicator_positions.csv"

COLUMNS = [
    "module", "subgroup", "indicator", "source_type", "extractor", "unit",
    "applies_to_industry", "position_type",
    # report-type position
    "selector_chain", "matched_selector", "matched_section",
    "toc_ordinal", "toc_level", "char_start", "char_end", "body_chars",
    # akshare-type position
    "statement", "field", "report_hint_section", "report_hint_ordinal",
    # computed-type position
    "formula", "inputs",
    # status
    "resolved", "note",
]


def _normalize(s: str) -> str:
    """Normalize an indicator name for matching: lowercase, strip spaces."""
    return (s or "").strip().replace(" ", "").lower()


def _build_rule_index(rules: list[dict]) -> dict[str, dict]:
    """Map every normalized name + alias to its rule.

    Non-``_coverage`` rules win over the computed ``*_coverage`` shadow rules
    when a name collides, so 拨贷比 resolves to the report rule, not the
    computed 拨贷比_coverage rule.
    """
    index: dict[str, dict] = {}
    # first pass: computed shadow rules (lowest priority)
    for r in rules:
        if r["name"].endswith("_coverage"):
            index.setdefault(_normalize(r["name"]), r)
            for a in r.get("aliases", []):
                index.setdefault(_normalize(a), r)
    # second pass: everything else (overwrites shadow collisions)
    for r in rules:
        if r["name"].endswith("_coverage"):
            continue
        index[_normalize(r["name"])] = r
        for a in r.get("aliases", []):
            index[_normalize(a)] = r
    return index


def _selector_chain(rule: dict) -> str:
    sels = (rule.get("source") or {}).get("selectors") or []
    parts = []
    for s in sels:
        label = s.get("section", "")
        if s.get("fallback"):
            label += " (fallback)"
        parts.append(label)
    return " → ".join(parts)


def _section_offsets(text: str, outline: list[dict], entry: dict) -> tuple[int, int, int]:
    """Return (char_start, char_end, body_chars) for an outline entry.

    Mirrors ``cnreport_tools.extract_section_text`` so offsets line up with the
    body the engine actually extracts.
    """
    start = T._find_section_start(text, entry["title"])
    if start == -1:
        token = entry["title"].split()[0] if entry["title"] else entry["title"]
        start = T._find_section_start(text, token)
    if start == -1:
        return -1, -1, 0
    body_start = text.find("\n", start)
    if body_start == -1:
        body_start = len(text)
    end = len(text)
    for e in outline:
        if e["ordinal"] <= entry["ordinal"]:
            continue
        pos = T._find_section_start(text, e["title"])
        if pos != -1 and pos >= body_start:
            end = pos
            break
    body = T.extract_section_text(text, outline, entry)
    return start, end, len(body)


def _resolve_report(text, outline, rule, stock_code):
    """Walk selectors via the engine; return a position dict for the matched entry."""
    body, matched = I._resolve_section(text, outline, rule, stock_code)
    if body is None:
        tried = " | ".join(matched) if isinstance(matched, list) else str(matched)
        return {
            "selector_chain": _selector_chain(rule),
            "matched_selector": "",
            "matched_section": "",
            "toc_ordinal": "",
            "toc_level": "",
            "char_start": "",
            "char_end": "",
            "body_chars": "",
            "resolved": "no",
            "note": f"section not found; tried: {tried}",
        }
    # re-resolve the matched selector to its outline entry for offsets
    entry = T.resolve_selector(outline, matched)
    if entry is None:
        return {
            "selector_chain": _selector_chain(rule),
            "matched_selector": matched,
            "matched_section": "",
            "toc_ordinal": "",
            "toc_level": "",
            "char_start": "",
            "char_end": "",
            "body_chars": len(body),
            "resolved": "partial",
            "note": "section body resolved but TOC entry not found for offsets",
        }
    cs, ce, bc = _section_offsets(text, outline, entry)
    return {
        "selector_chain": _selector_chain(rule),
        "matched_selector": matched,
        "matched_section": entry["title"],
        "toc_ordinal": entry["ordinal"],
        "toc_level": entry["level"],
        "char_start": cs,
        "char_end": ce,
        "body_chars": bc,
        "resolved": "yes",
        "note": "",
    }


def _resolve_akshare(outline, rule):
    src = rule.get("source") or {}
    statement = src.get("statement", "")
    field = src.get("field", "")
    entry = T.resolve_statement(outline, statement)
    return {
        "statement": statement,
        "field": field,
        "report_hint_section": entry["title"] if entry else "",
        "report_hint_ordinal": entry["ordinal"] if entry else "",
        "resolved": "yes" if entry else "no",
        "note": ("akshare-sourced; report hint is the matched TOC section "
                 f"({statement}).") if entry else "akshare-sourced; no report section matched",
    }


def _resolve_computed(rule):
    src = rule.get("source") or {}
    return {
        "formula": src.get("formula", ""),
        "inputs": " | ".join(src.get("inputs", [])),
        "resolved": "n/a",
        "note": "computed locally; no report position",
    }


def main() -> int:
    text = REPORT_TXT.read_text(encoding="utf-8")
    outline = T.parse_outline(text)
    print(f"report: {REPORT_TXT.name}  chars={len(text)}  outline={len(outline)}")

    rules = json.loads(RULES_JSON.read_text(encoding="utf-8"))["rules"]
    rule_index = _build_rule_index(rules)
    coverage = list(csv.DictReader(COVERAGE_CSV.open(encoding="utf-8")))
    fetchable = [r for r in coverage if r["fetchable"].strip().lower() == "yes"]
    print(f"coverage fetchable rows: {len(fetchable)}  rules: {len(rules)}")

    rows = []
    unresolved = []
    for cov in fetchable:
        name = cov["indicator"]
        rule = rule_index.get(_normalize(name))
        if rule is None:
            rows.append({
                "module": cov["module"], "subgroup": cov["subgroup"],
                "indicator": name, "source_type": cov["source_type"],
                "extractor": cov["extractor"], "unit": "",
                "applies_to_industry": "",
                "position_type": "unknown",
                "resolved": "no",
                "note": "no rule found in indicator_rules.json",
            })
            unresolved.append(name)
            continue

        industry = (rule.get("applies_to") or {}).get("industry", "")
        base = {
            "module": cov["module"], "subgroup": cov["subgroup"],
            "indicator": name, "source_type": rule.get("source_type", cov["source_type"]),
            "extractor": rule.get("extractor", cov["extractor"]),
            "unit": rule.get("unit", ""),
            "applies_to_industry": industry,
        }
        st = rule.get("source_type")
        if st == "report":
            pos = _resolve_report(text, outline, rule, STOCK_CODE)
            base["position_type"] = "section"
        elif st == "akshare":
            pos = _resolve_akshare(outline, rule)
            base["position_type"] = "akshare_api"
        elif st == "computed":
            pos = _resolve_computed(rule)
            base["position_type"] = "derived"
        else:
            pos = {"resolved": "no", "note": f"unknown source_type: {st}"}
            base["position_type"] = "unknown"
        base.update(pos)
        rows.append(base)
        if pos.get("resolved") in ("no", "partial"):
            unresolved.append(name)

    # write CSV
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})

    # summary
    from collections import Counter
    by_type = Counter(r["position_type"] for r in rows)
    by_res = Counter(r["resolved"] for r in rows)
    print(f"\nwrote {len(rows)} rows → {OUT_CSV.relative_to(_REPO_ROOT)}")
    print(f"by position_type: {dict(by_type)}")
    print(f"by resolved:      {dict(by_res)}")
    if unresolved:
        print(f"unresolved ({len(unresolved)}): {unresolved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
