"""CSV → indicator_rules.json migration for cnreport-mcp.

``docs/indicators_position.csv`` is the maintained human-editable catalog of
indicators and where each one lives in a periodic report (``section_en`` /
``section_cn``) and which report types contain it (``report_type``). This
module converts each CSV row into a rule in ``indicator_rules.json`` so the
existing engine (``indicators_client``) can reach all of them.

Mapping (deterministic — no per-rule hand-authoring)::

    indicator        → name
    indicator_cn     → alias (English)
    section_en       → module  (Balance Sheet → balance_sheet, …)
    section_cn       → subgroup + selectors[]
    report_type       → source_type classification + period_type + report_type

Classification (Decision 2):

    periodic (年报/半年报/季报/年度) → source_type "report"
    实时 (realtime market data)      → source_type "external"

Reconciliation (Decision 3 — overlap with the hand-authored banking rules):

    * A CSV row whose ``indicator`` matches an existing rule's ``name``
      ANNOTATES that rule (``report_type`` + the English alias) without
      discarding its richer ``selectors[]`` / ``applies_to`` / ``direction``.
    * CSV-only indicators become new ``source_type: "report"`` (or
      ``"external"``) rules, appended after the hand-authored ones.
    * The migration is idempotent: re-running over an unchanged CSV reproduces
      the same JSON. Previously migrated CSV-sourced rules (tagged
      ``_csv_source: true``) are dropped and regenerated; hand-authored rules
      are preserved in their original order.

Public entry points::

    csv_row_to_rule(row)          # one CSV row → a rule dict
    migrate(csv_path, rules_path) # reconcile CSV into the rule set (in place)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_CSV = _REPO_ROOT / "docs" / "indicators_position.csv"
_DEFAULT_RULES = _REPO_ROOT / "indicator_rules.json"

# CSV-sourced rules carry this marker so a re-run can drop and regenerate them
# without touching hand-authored rules.
_CSV_SOURCE_KEY = "_csv_source"
_CSV_ANNOTATED_KEY = "_csv_annotated"

# statement module → the canonical statement title used as the selector. The
# regex pass in ``cnreport_tools.resolve_selector`` matches "合并资产负债表" etc.
_STATEMENT_KEYWORD: dict[str, str] = {
    "balance_sheet": "资产负债表",
    "income_statement": "利润表",
    "cashflow": "现金流量表",
}

# Section prefixes (section_en) that are narrative prose rather than tables →
# the LLM extractor is the better default.
_NARRATIVE_SECTION_PREFIXES = (
    "Management Discussion",
    "Risk Management",
    "Notes to Financial Statements",
    "Customer Information",
    "Supplier Information",
    "Segment Information",
    "Shareholders Information",
    "Share Changes",
    "Important Matters",
    "Financing Information",
)

# Market-data / external sections — indicator not present in the report PDF.
_EXTERNAL_SECTIONS = ("Market Data", "Fund Holdings")


# ── classification helpers ────────────────────────────────────────


def _classify_source_type(report_type: str, section_en: str = "") -> str:
    """Map a CSV ``report_type`` (+ section hint) to a rule ``source_type``."""
    rt = report_type or ""
    if "实时" in rt:
        return "external"
    # sections flagged external even without 实时
    if any(section_en.strip().startswith(p) for p in _EXTERNAL_SECTIONS):
        return "external"
    return "report"


def _map_module(section_en: str, section_cn: str, source_type: str) -> str:
    """Derive the rule module from ``section_en``."""
    se = (section_en or "").strip()
    if se.startswith("Balance Sheet"):
        return "balance_sheet"
    if se.startswith("Income Statement"):
        return "income_statement"
    if se.startswith("Cash Flow Statement"):
        return "cashflow"
    if se.startswith("Statement of Comprehensive Income"):
        return "income_statement"
    if se.startswith("Computed"):
        return "financial_ratio"
    if source_type == "external":
        return "market_data"
    return "report_section"


def _infer_period_type(report_type: str) -> str:
    rt = report_type or ""
    if "实时" in rt:
        return "realtime"
    if "年报" in rt or "年度" in rt:
        return "annual"
    if "季报" in rt:
        return "quarterly"
    return "annual"


def _infer_extractor(
    indicator: str, section_en: str, section_cn: str, module: str, source_type: str,
) -> str:
    """Pick a sensible default extractor for a CSV-sourced rule.

    Percent/ratio names → ``python:percent_value``; HR headcount →
    ``python:headcount``; statement line items → ``python:table_row``;
    narrative sections → ``llm``; ``external`` rules carry no extractor.
    """
    if source_type == "external":
        return ""
    name = indicator or ""
    se = (section_en or "").strip()
    if any(name.endswith(s) or s in name for s in ("率", "比率", "比例", "占比")):
        return "python:percent_value"
    if se.startswith("Human Resources") or any(k in name for k in ("员工", "人数", "在职")):
        return "python:headcount"
    if module in _STATEMENT_KEYWORD:
        return "python:table_row"
    if any(se.startswith(p) for p in _NARRATIVE_SECTION_PREFIXES):
        return "llm"
    return "auto"


def _infer_unit(indicator: str, section_en: str, source_type: str, extractor: str) -> str:
    if source_type == "external":
        return ""
    name = indicator or ""
    if extractor == "python:percent_value" or name.endswith("率") or "比率" in name or "比例" in name:
        return "%"
    if extractor == "python:headcount":
        return "人"
    if "股" in name and "股东" not in name:
        return "股"
    return "元"


def _build_selectors(section_en: str, section_cn: str, module: str) -> list[dict]:
    """Build the ``selectors[]`` chain for a CSV-sourced report rule.

    Statement modules resolve to the canonical statement title (matched via
    the regex pass against "合并资产负债表" etc.); non-statement modules use
    the descriptive ``section_cn`` (matched via the normalized-substring pass
    added to ``resolve_selector``).
    """
    if module in _STATEMENT_KEYWORD:
        return [{"section": _STATEMENT_KEYWORD[module], "fallback": True}]
    return [{"section": section_cn, "fallback": True}]


# ── row → rule ─────────────────────────────────────────────────────


def csv_row_to_rule(row: dict) -> dict:
    """Convert one CSV row into a rule dict (Decision 1)."""
    indicator = (row.get("indicator") or "").strip()
    indicator_cn = (row.get("indicator_cn") or "").strip()
    section_en = (row.get("section_en") or "").strip()
    section_cn = (row.get("section_cn") or "").strip()
    report_type = (row.get("report_type") or "").strip()

    source_type = _classify_source_type(report_type, section_en)
    module = _map_module(section_en, section_cn, source_type)
    extractor = _infer_extractor(indicator, section_en, section_cn, module, source_type)
    unit = _infer_unit(indicator, section_en, source_type, extractor)
    selectors = _build_selectors(section_en, section_cn, module) if source_type == "report" else []

    aliases = [indicator_cn] if indicator_cn and indicator_cn != indicator else []

    rule: dict[str, Any] = {
        "name": indicator,
        "aliases": aliases,
        "module": module,
        "subgroup": section_cn or section_en,
        "applies_to": {
            "industry": "*",
            "sub_types": ["*"],
            "companies": ["*"],
            "exclude_companies": [],
        },
        "source_type": source_type,
        "extractor": extractor,
        "unit": unit,
        "period_type": _infer_period_type(report_type),
        "direction": "none",
        "report_type": report_type,
        "note": f"sourced from indicators_position.csv (section: {section_cn or section_en})",
        _CSV_SOURCE_KEY: True,
    }
    if source_type == "report":
        rule["source"] = {"selectors": selectors, "extractor": extractor}
    elif source_type == "external":
        # external rules carry no selectors/extractor (not extractable from the report)
        rule["source"] = {}
    return rule


# ── reconciliation ─────────────────────────────────────────────────


def _read_csv(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    """One row per indicator name (first occurrence wins)."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        name = (r.get("indicator") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(r)
    return out


def _annotate_existing(rule: dict, row: dict) -> bool:
    """Annotate a hand-authored rule with the CSV's ``report_type`` + alias.

    Returns True if the rule was modified. Idempotent: re-annotating with the
    same values is a no-op.
    """
    changed = False
    rt = (row.get("report_type") or "").strip()
    if rt and rule.get("report_type") != rt:
        rule["report_type"] = rt
        changed = True
    cn = (row.get("indicator_cn") or "").strip()
    if cn and cn != rule.get("name"):
        aliases = list(rule.get("aliases") or [])
        if cn not in aliases:
            aliases.append(cn)
            rule["aliases"] = aliases
            changed = True
    if not rule.get(_CSV_ANNOTATED_KEY):
        rule[_CSV_ANNOTATED_KEY] = True
        changed = True
    return changed


def migrate(
    csv_path: Path | str = _DEFAULT_CSV,
    rules_path: Path | str = _DEFAULT_RULES,
    *,
    dry_run: bool = False,
) -> dict:
    """Reconcile ``docs/indicators_position.csv`` into ``indicator_rules.json``.

    Appends CSV-only rules, annotates overlapping rules, preserves hand-authored
    rules, and is idempotent. Returns a summary dict
    ``{total, hand_authored, csv_sourced, annotated, added, changed_file}``.
    When ``dry_run`` is set, the rules file is NOT written; ``changed_file``
    reports whether it would have changed.
    """
    csv_path = Path(csv_path)
    rules_path = Path(rules_path)
    rows = _dedupe_rows(_read_csv(csv_path))

    data = json.loads(rules_path.read_text(encoding="utf-8"))
    rules: list[dict] = data.get("rules", [])
    schema = data.get("_schema", {})
    source = data.get("_source", "")

    existing_by_name: dict[str, dict] = {}
    for r in rules:
        if r.get("name"):
            existing_by_name.setdefault(r["name"], r)

    # drop previously-migrated CSV-sourced rules (regenerated below)
    hand_authored: list[dict] = [r for r in rules if not r.get(_CSV_SOURCE_KEY)]

    annotated = 0
    csv_only_rows: list[dict] = []
    for row in rows:
        name = (row.get("indicator") or "").strip()
        existing = existing_by_name.get(name)
        if existing is not None and not existing.get(_CSV_SOURCE_KEY):
            if _annotate_existing(existing, row):
                annotated += 1
        else:
            csv_only_rows.append(row)

    added = 0
    new_rules: list[dict] = []
    for row in csv_only_rows:
        new_rules.append(csv_row_to_rule(row))
        added += 1

    final_rules = hand_authored + new_rules
    data["rules"] = final_rules
    data["_schema"] = schema
    _migration_note = (
        " CSV-sourced indicators are migrated from docs/indicators_position.csv"
        " by indicators_csv_migration.migrate (idempotent; re-run after editing the CSV)."
    )
    if _migration_note not in (source or ""):
        data["_source"] = (source or "").rstrip() + _migration_note

    summary = {
        "total": len(final_rules),
        "hand_authored": len(hand_authored),
        "csv_sourced": len(new_rules),
        "annotated": annotated,
        "added": added,
    }

    if dry_run:
        new_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        old_text = rules_path.read_text(encoding="utf-8")
        summary["changed_file"] = new_text != old_text
        summary["dry_run"] = True
        return summary

    rules_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary["changed_file"] = True
    summary["rules_path"] = str(rules_path)
    return summary


def _main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Migrate indicators_position.csv into indicator_rules.json")
    p.add_argument("--csv", default=str(_DEFAULT_CSV), help="Position CSV path")
    p.add_argument("--rules", default=str(_DEFAULT_RULES), help="indicator_rules.json path")
    p.add_argument("--check", action="store_true", help="Dry-run: report whether the file would change")
    args = p.parse_args()
    summary = migrate(args.csv, args.rules, dry_run=args.check)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.check and not summary["changed_file"]:
        print("✓ indicator_rules.json is up to date with the CSV")


if __name__ == "__main__":
    _main()
