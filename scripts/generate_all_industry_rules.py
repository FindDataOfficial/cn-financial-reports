#! /usr/bin/env python3
"""Generate LLM + script rules for ALL industries in the taxonomy.

For each industry with a baseline in industry_indicator_baseline.json,
generates LLM rules and script rules using the existing generator skills.
Rules are persisted to the rules database.

Usage:
    python scripts/generate_all_industry_rules.py
    python scripts/generate_all_industry_rules.py --industry 801120
    python scripts/generate_all_industry_rules.py --country cn
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT.parent / ".env")          # root .env (finddata/)
    load_dotenv(_REPO_ROOT / ".env", override=True)  # cnreport/.env overrides
except ImportError:
    pass

import industry_coverage as C  # noqa: E402
import industry_taxonomy as IT  # noqa: E402
import rules_db  # noqa: E402
from rules_skills import LlmRulesOutput, ScriptRulesOutput, generate_and_persist  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate LLM + script rules for all industries.")
    p.add_argument("--industry", help="Filter to one Shenwan L1 code (e.g. 801120)")
    p.add_argument("--country", default="cn", help="Country: cn or hk (default: cn)")
    p.add_argument("--taxonomy", default=str(IT.default_taxonomy_path()), help="Path to industry_taxonomy.json")
    p.add_argument("--baseline", default=str(C.default_baseline_path()), help="Path to industry_indicator_baseline.json")
    p.add_argument("--llm-only", action="store_true", help="Only generate LLM rules, skip script rules")
    p.add_argument("--script-only", action="store_true", help="Only generate script rules, skip LLM rules")
    p.add_argument("--skip-existing", action="store_true", help="Skip document_types that already have rules")
    return p.parse_args(argv)


def _count_rules(document_type: str) -> tuple[int, int]:
    """Return (llm_count, script_count) for a document_type."""
    llm_set = C.existing_llm_indicators(document_type)
    script_set = C.existing_script_indicators(document_type)
    return len(llm_set), len(script_set)


def _build_llm_prompt(document_type: str, label: str, indicators: list[str]) -> tuple[str, str]:
    """Build LLM system+user prompts for generating rules for one document_type."""
    system = (
        "You are a financial report analyst specializing in Chinese listed company annual reports. "
        "Generate LLM extraction rules for a specific industry and document type. "
        "Each rule must include: indicator (Chinese name), instruction (how to extract from the report), "
        "position (which section/table to look at), document_type, module (balance_sheet, "
        "income_statement, cashflow, financial_ratio, or report_section), "
        "subgroup, unit, and period_type. "
        "Return ONLY valid JSON: {\"rules\": [...]}."
    )
    indicators_json = json.dumps(indicators, ensure_ascii=False)
    user = (
        f"Industry: {label} ({document_type})\n\n"
        f"Required indicators ({len(indicators)}):\n{indicators_json}\n\n"
        "For each indicator, determine which financial statement module it belongs to "
        "(balance_sheet, income_statement, cashflow, financial_ratio, or report_section) "
        "and provide detailed extraction instructions. Be specific about which section "
        "of the annual report to find each indicator.\n\n"
        "Return JSON: {\"rules\": [...]}."
    )
    return system, user


def _build_script_prompt(document_type: str, llm_rules: list[dict]) -> tuple[str, str]:
    """Build prompts for generating script rules from LLM rules."""
    import script_extractors
    available = ", ".join(script_extractors.names())
    system = (
        "You choose deterministic Python extractors for financial indicators. "
        f"Available extractors: {available}. For each indicator, produce one script rule: "
        "extract_rule (one of the available names), position (selectors), document_type, "
        "indicator. Return JSON: {\"rules\": [...]}."
    )
    user = (
        f"document_type: {document_type}\n\n"
        f"Indicators ({len(llm_rules)}):\n"
        + json.dumps(
            [{"indicator": r.get("name") or r.get("indicator"),
              "module": r.get("module"), "unit": r.get("unit"),
              "position": r.get("position")} for r in llm_rules],
            ensure_ascii=False, indent=2,
        )[:12000]
        + "\n\nReturn a JSON object {\"rules\": [...]} with one script rule per indicator."
    )
    return system, user


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    tax = IT.load_taxonomy(args.taxonomy)
    baselines = C.load_baselines(args.baseline)

    # Build the list of document types to process
    entries = IT.list_document_types(tax, industry=args.industry, country=args.country)
    # Only process annual-report types (those have baselines)
    entries = [e for e in entries if e.report_kind == "annual-report"]

    results: list[dict] = []
    for entry in entries:
        dt = entry.document_type
        indicators = baselines.get(dt, [])
        if not indicators:
            print(f"SKIP {dt}: no baseline indicators defined")
            results.append({"document_type": dt, "status": "skipped", "reason": "no baseline"})
            continue

        existing_llm, existing_script = _count_rules(dt)
        if args.skip_existing and existing_llm >= len(indicators):
            print(f"SKIP {dt}: already has {existing_llm}/{len(indicators)} LLM rules")
            results.append({"document_type": dt, "status": "skipped", "reason": "already has rules"})
            continue

        print(f"\n{'='*60}")
        print(f"Processing: {dt} ({entry.label})")
        print(f"  indicators: {len(indicators)} (existing LLM rules: {existing_llm})")

        # Step 1: Generate LLM rules (if not already covered)
        if not args.script_only:
            llm_system, llm_user = _build_llm_prompt(dt, entry.label, indicators)
            print(f"  Generating LLM rules for {len(indicators)} indicators...")
            try:
                result = generate_and_persist(
                    llm_system, llm_user, LlmRulesOutput,
                    rules_db.upsert_llm_rule,
                    "fd-cnreport-llm-rules-creator",
                )
                print(f"  ✓ Generated {result['count']} LLM rules")
            except Exception as e:
                print(f"  ✗ LLM rule generation failed: {e}")
                results.append({"document_type": dt, "status": "failed", "step": "llm", "error": str(e)})
                continue

        # Step 2: Generate script rules from LLM rules
        if not args.llm_only:
            llm_rules_for_dt = _read_llm_rules(dt)
            if not llm_rules_for_dt:
                print(f"  SKIP script rules: no LLM rules found for {dt}")
                results.append({"document_type": dt, "status": "skipped", "step": "script", "reason": "no LLM rules"})
                continue

            script_system, script_user = _build_script_prompt(dt, llm_rules_for_dt)
            print(f"  Generating script rules for {len(llm_rules_for_dt)} indicators...")
            try:
                result = generate_and_persist(
                    script_system, script_user, ScriptRulesOutput,
                    rules_db.upsert_script_rule,
                    "fd-cnreport-pdf-scripts-by-type-creator",
                )
                print(f"  ✓ Generated {result['count']} script rules")
            except Exception as e:
                print(f"  ✗ Script rule generation failed: {e}")
                results.append({"document_type": dt, "status": "failed", "step": "script", "error": str(e)})
                continue

        # Step 3: Check coverage
        rep = C.check_coverage(dt, indicators)
        status = "supported" if rep.supported else "partial"
        print(f"  Status: {status} (llm_ready={rep.llm_ready}, script_ready={rep.script_ready})")
        results.append({
            "document_type": dt,
            "status": status,
            "llm_ready": rep.llm_ready,
            "script_ready": rep.script_ready,
            "llm_rules": _count_rules(dt),
        })

        time.sleep(1)  # rate limit between industries

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    supported = sum(1 for r in results if r.get("status") == "supported")
    failed = sum(1 for r in results if r.get("status") == "failed" or r.get("status") == "partial" and r.get("llm_rules", (0,0))[0] == 0)
    print(f"  Total: {len(results)}")
    print(f"  Supported: {supported}")
    print(f"  Failed: {failed}")

    # Save report
    out_path = _REPO_ROOT / "docs" / "industry_rule_generation_report.json"
    out_path.write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Report saved to {out_path}")
    return 0 if failed == 0 else 1


def _read_llm_rules(document_type: str) -> list[dict]:
    """Read all LLM rules for a document_type from the database."""
    from cnreport_models import LlmRule
    rows: list[dict] = []
    with rules_db._session() as session:
        for row in (
            session.query(LlmRule)
            .filter(LlmRule.document_type == document_type)
            .order_by(LlmRule.module, LlmRule.indicator)
            .all()
        ):
            rows.append(row.to_rule_dict())
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
