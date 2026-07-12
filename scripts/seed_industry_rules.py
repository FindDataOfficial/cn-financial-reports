#! /usr/bin/env python3
"""Seed the rules database with industry-specific LLM and script rules.

This script defines the key financial modules and indicators for each
申万 L1 industry based on domain knowledge, and persists them to the
llm_rules and script_rules tables.

Usage:
    python scripts/seed_industry_rules.py
    python scripts/seed_industry_rules.py --document-type cn/801120/listed/annual-report
    python scripts/seed_industry_rules.py --country hk
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import cnreport_database  # noqa: E402
import rules_db  # noqa: E402
from cnreport_models import LlmRule, ScriptRule  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed industry rules into the database.")
    p.add_argument("--document-type", help="Only seed rules for this specific document_type")
    p.add_argument("--country", default="cn", help="Country: cn or hk (default: cn)")
    p.add_argument("--seed-file", default=str(_REPO_ROOT / "scripts" / "industry_rules_data.json"),
                   help="Path to the rules data JSON file")
    return p.parse_args(argv)


def _build_universal_rules() -> list[dict]:
    """Build LLM rules for universal financial indicators that apply to all industries.

    These are the common indicators found in every company's three major financial
    statements (三大报表).
    """
    rules: list[dict] = []

    # ── Balance Sheet (资产负债表) modules ──
    bs_indicators = [
        {"indicator": "资产总计", "instruction": "从资产负债表末尾行找到资产总计金额, 通常为合并资产负债表的最后一行", "subgroup": "资产总计", "unit": "元", "position": "[\"合并资产负债表\"]"},
        {"indicator": "流动资产合计", "instruction": "从资产负债表的流动资产部分找到流动资产合计金额", "subgroup": "流动资产", "unit": "元", "position": "[\"合并资产负债表\"]"},
        {"indicator": "货币资金", "instruction": "从资产负债表的流动资产部分找到货币资金金额", "subgroup": "流动资产", "unit": "元", "position": "[\"合并资产负债表\"]"},
        {"indicator": "应收账款", "instruction": "从资产负债表的流动资产部分找到应收账款金额", "subgroup": "流动资产", "unit": "元", "position": "[\"合并资产负债表\"]"},
        {"indicator": "存货", "instruction": "从资产负债表的流动资产部分找到存货金额", "subgroup": "流动资产", "unit": "元", "position": "[\"合并资产负债表\"]"},
        {"indicator": "固定资产", "instruction": "从资产负债表的非流动资产部分找到固定资产金额", "subgroup": "非流动资产", "unit": "元", "position": "[\"合并资产负债表\"]"},
        {"indicator": "负债合计", "instruction": "从资产负债表末尾行找到负债合计金额", "subgroup": "负债合计", "unit": "元", "position": "[\"合并资产负债表\"]"},
        {"indicator": "流动负债合计", "instruction": "从资产负债表的流动负债部分找到流动负债合计金额", "subgroup": "流动负债", "unit": "元", "position": "[\"合并资产负债表\"]"},
        {"indicator": "所有者权益合计", "instruction": "从资产负债表末尾行找到所有者权益合计金额", "subgroup": "所有者权益合计", "unit": "元", "position": "[\"合并资产负债表\"]"},
    ]

    # ── Income Statement (利润表) modules ──
    is_indicators = [
        {"indicator": "营业收入", "instruction": "从利润表的第一行找到营业收入/营业总收入金额", "subgroup": "营业收入", "unit": "元", "position": "[\"合并利润表\"]"},
        {"indicator": "营业成本", "instruction": "从利润表的营业收入下方找到营业成本金额", "subgroup": "营业成本", "unit": "元", "position": "[\"合并利润表\"]"},
        {"indicator": "销售费用", "instruction": "从利润表中找到销售费用金额", "subgroup": "期间费用", "unit": "元", "position": "[\"合并利润表\"]"},
        {"indicator": "管理费用", "instruction": "从利润表中找到管理费用金额", "subgroup": "期间费用", "unit": "元", "position": "[\"合并利润表\"]"},
        {"indicator": "研发费用", "instruction": "从利润表中找到研发费用金额", "subgroup": "期间费用", "unit": "元", "position": "[\"合并利润表\"]"},
        {"indicator": "财务费用", "instruction": "从利润表中找到财务费用金额", "subgroup": "期间费用", "unit": "元", "position": "[\"合并利润表\"]"},
        {"indicator": "投资收益", "instruction": "从利润表中找到投资收益金额", "subgroup": "投资收益", "unit": "元", "position": "[\"合并利润表\"]"},
        {"indicator": "营业利润", "instruction": "从利润表中找到营业利润金额", "subgroup": "营业利润", "unit": "元", "position": "[\"合并利润表\"]"},
        {"indicator": "利润总额", "instruction": "从利润表中找到利润总额金额", "subgroup": "利润总额", "unit": "元", "position": "[\"合并利润表\"]"},
        {"indicator": "净利润", "instruction": "从利润表末尾找到净利润金额, 通常为归属于母公司股东的净利润", "subgroup": "净利润", "unit": "元", "position": "[\"合并利润表\"]"},
    ]

    # ── Cash Flow (现金流量表) modules ──
    cf_indicators = [
        {"indicator": "经营活动产生的现金流量净额", "instruction": "从现金流量表的经营活动部分找到经营活动现金流量净额", "subgroup": "经营活动现金流", "unit": "元", "position": "[\"合并现金流量表\"]"},
        {"indicator": "投资活动产生的现金流量净额", "instruction": "从现金流量表的投资活动部分找到投资活动现金流量净额", "subgroup": "投资活动现金流", "unit": "元", "position": "[\"合并现金流量表\"]"},
        {"indicator": "筹资活动产生的现金流量净额", "instruction": "从现金流量表的筹资活动部分找到筹资活动现金流量净额", "subgroup": "筹资活动现金流", "unit": "元", "position": "[\"合并现金流量表\"]"},
        {"indicator": "现金及现金等价物净增加额", "instruction": "从现金流量表末尾找到现金及现金等价物净增加额", "subgroup": "现金净变动", "unit": "元", "position": "[\"合并现金流量表\"]"},
    ]

    # ── Financial Ratios (财务指标) ──
    fr_indicators = [
        {"indicator": "基本每股收益", "instruction": "从利润表或财务指标部分找到基本每股收益", "subgroup": "每股指标", "unit": "元/股", "position": "[\"合并利润表\", \"每股收益\"]"},
        {"indicator": "净资产收益率", "instruction": "从财务指标部分找到加权平均净资产收益率", "subgroup": "盈利能力", "unit": "%", "position": "[\"财务指标\", \"主要财务指标\"]"},
        {"indicator": "资产负债率", "instruction": "计算: 负债合计 / 资产总计 * 100%, 或直接从财务指标部分读取", "subgroup": "偿债能力", "unit": "%", "position": "[\"财务指标\", \"合并资产负债表\"]"},
        {"indicator": "毛利率", "instruction": "计算: (营业收入 - 营业成本) / 营业收入 * 100%, 或直接从财务指标部分读取", "subgroup": "盈利能力", "unit": "%", "position": "[\"财务指标\", \"合并利润表\"]"},
        {"indicator": "净利润率", "instruction": "计算: 净利润 / 营业收入 * 100%, 或直接从财务指标部分读取", "subgroup": "盈利能力", "unit": "%", "position": "[\"财务指标\", \"合并利润表\"]"},
    ]

    for r in bs_indicators + is_indicators + cf_indicators + fr_indicators:
        module = "balance_sheet" if r in bs_indicators else \
                 "income_statement" if r in is_indicators else \
                 "cashflow" if r in cf_indicators else "financial_ratio"
        rules.append({
            **r,
            "module": module,
            "source_type": "report",
            "extractor": "llm",
            "applies_to": {"industry": "*"},
            "period_type": "annual",
        })

    return rules


def _build_script_rules() -> list[dict]:
    """Build script rules that map indicators to deterministic extractors."""
    rules: list[dict] = []

    # regex_amount extractors (simple number extraction from text)
    regex_indicators = [
        "资产总计", "流动资产合计", "货币资金", "应收账款", "存货",
        "固定资产", "负债合计", "流动负债合计", "所有者权益合计",
        "营业收入", "营业成本", "销售费用", "管理费用", "研发费用",
        "财务费用", "投资收益", "营业利润", "利润总额", "净利润",
        "经营活动产生的现金流量净额", "投资活动产生的现金流量净额",
        "筹资活动产生的现金流量净额", "现金及现金等价物净增加额",
        "基本每股收益",
    ]
    for ind in regex_indicators:
        rules.append({
            "indicator": ind,
            "extract_rule": "regex_amount",
            "position": "",
            "module": "",
            "source_type": "report",
        })

    # percent_value extractors (percentage values)
    pct_indicators = ["净资产收益率", "毛利率", "净利润率", "资产负债率"]
    for ind in pct_indicators:
        rules.append({
            "indicator": ind,
            "extract_rule": "percent_value",
            "position": "",
            "module": "financial_ratio",
            "source_type": "report",
        })

    return rules


def _apply_to_document_types() -> list[str]:
    """Return the list of all document types to seed rules for."""
    import industry_taxonomy as IT
    tax = IT.load_taxonomy()
    entries = IT.list_document_types(tax, country="cn")
    hk_entries = IT.list_document_types(tax, country="hk")
    # All periodic report types (annual, interim, quarterly) get the same universal rules
    return [e.document_type for e in entries + hk_entries]


def _seed_rules_for_dt(
    dt: str,
    llm_rules: list[dict],
    script_rules: list[dict],
) -> dict:
    """Seed LLM and script rules for one document_type.
    
    Returns {llm_inserted, script_inserted, llm_existing, script_existing}.
    """
    with rules_db._session() as session:
        llm_inserted = 0
        script_inserted = 0
        llm_existing = 0
        script_existing = 0

        # Seed LLM rules
        for r in llm_rules:
            existing = (
                session.query(LlmRule)
                .filter(LlmRule.indicator == r["indicator"], LlmRule.document_type == dt)
                .first()
            )
            if existing is None:
                session.add(LlmRule(
                    indicator=r["indicator"],
                    document_type=dt,
                    module=r.get("module"),
                    subgroup=r.get("subgroup"),
                    source_type=r.get("source_type", "report"),
                    extractor=r.get("extractor", "llm"),
                    applies_to=r.get("applies_to", {"industry": "*"}),
                    unit=r.get("unit", ""),
                    period_type=r.get("period_type", "annual"),
                    instruction=r.get("instruction", ""),
                    position=r.get("position", ""),
                ))
                llm_inserted += 1
            else:
                # Update instruction/position if missing
                if not existing.instruction and r.get("instruction"):
                    existing.instruction = r["instruction"]
                if not existing.position and r.get("position"):
                    existing.position = r["position"]
                llm_existing += 1

        # Seed script rules
        for r in script_rules:
            existing = (
                session.query(ScriptRule)
                .filter(ScriptRule.indicator == r["indicator"], ScriptRule.document_type == dt)
                .first()
            )
            if existing is None:
                session.add(ScriptRule(
                    indicator=r["indicator"],
                    document_type=dt,
                    extract_rule=r.get("extract_rule", ""),
                    position=r.get("position", ""),
                    module=r.get("module", ""),
                    source_type=r.get("source_type", "report"),
                ))
                script_inserted += 1
            else:
                script_existing += 1

        session.commit()

    return {
        "llm_inserted": llm_inserted,
        "script_inserted": script_inserted,
        "llm_existing": llm_existing,
        "script_existing": script_existing,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    
    llm_rules = _build_universal_rules()
    script_rules = _build_script_rules()
    
    print(f"Built {len(llm_rules)} universal LLM rules and {len(script_rules)} script rule templates")

    # Determine which document types to seed
    if args.document_type:
        doc_types = [args.document_type]
    else:
        doc_types = _apply_to_document_types()
    
    # Filter by country if specified
    if args.country:
        doc_types = [dt for dt in doc_types if dt.startswith(f"{args.country}/")]
    
    print(f"Seeding rules for {len(doc_types)} document types...")

    total_llm = 0
    total_script = 0
    for dt in doc_types:
        result = _seed_rules_for_dt(dt, llm_rules, script_rules)
        total_llm += result["llm_inserted"]
        total_script += result["script_inserted"]
        print(f"  {dt}: {result['llm_inserted']} LLM rules inserted ({result['llm_existing']} existing), "
              f"{result['script_inserted']} script rules inserted ({result['script_existing']} existing)")

    # Clear cache so the extraction pipeline sees the new rules
    rules_db.invalidate_rules_cache()

    print(f"\nDone. Total new LLM rules: {total_llm}, total new script rules: {total_script}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
