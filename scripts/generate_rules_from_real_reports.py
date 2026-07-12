#! /usr/bin/env python3
"""Generate industry-specific LLM rules focusing on industry-unique sections.

Strategy:
1. Generate universal rules from one representative industry (食品饮料)
2. For each industry, extract only the sections with industry-specific indicators
3. Combine universal + industry-specific → complete rule set

Usage:
    python scripts/generate_rules_from_real_reports.py
    python scripts/generate_rules_from_real_reports.py --industry 801120
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT.parent / ".env")
    load_dotenv(_REPO_ROOT / ".env", override=True)
except ImportError:
    pass

import httpx
import cninfo_client
import report_cache
import rules_db
from cnreport_models import LlmRule

# ── Representative companies ──
REP_COMPANY = {
    "801120": ("600519", "贵州茅台", "食品饮料"),
    "801780": ("601398", "工商银行", "银行"),
    "801180": ("600048", "保利发展", "房地产"),
    "801730": ("300750", "宁德时代", "电力设备"),
    "801150": ("600276", "恒瑞医药", "医药生物"),
    "801790": ("601318", "中国平安", "非银金融"),
}

# ── Industry-specific sections to extract ──
# Each entry: (section_title_keywords, what_to_look_for, guidance)
INDUSTRY_SECTIONS = {
    "801780": [  # 银行
        ("贷款五级分类", "五级分类", "信用风险", "贷款五级分类分布、不良率、拨备覆盖率"),
        ("净息差", "净息差", "净利差", "净息差、净利差、生息资产收益率、付息负债成本率"),
        ("资本充足率", "资本充足率", "资本构成", "资本充足率、核心一级资本充足率、杠杆率"),
        ("客户存款", "存款", "客户存款", "存款余额、存款结构、活期/定期占比"),
        ("贷款及垫款", "贷款", "贷款及垫款", "贷款余额、贷款结构、按行业/地区分布"),
    ],
    "801180": [  # 房地产
        ("合同负债", "合同负债", "预收款项", "合同负债（预收房款）、预收款项、预收账款"),
        ("存货开发成本", "开发成本", "开发产品", "开发成本明细、开发产品、拟开发土地"),
        ("销售面积", "销售面积", "签约面积", "签约销售面积、签约销售金额、结算面积"),
        ("土储", "土地储备", "规划计容", "土地储备面积、新增土储、规划计容建筑面积"),
    ],
    "801730": [  # 电力设备
        ("研发费用", "研发投入", "研发费用", "研发费用、研发投入占营收比例、研发人员"),
        ("产能利用率", "产能利用率", "产能", "产能利用率、在建产能、设计产能"),
        ("在建工程", "在建工程", "工程进度", "在建工程明细、工程进度、预算数"),
        ("应收账款", "应收账款", "账龄", "应收账款、应收票据、应收账款账龄分析"),
    ],
    "801150": [  # 医药生物
        ("研发费用", "研发投入", "研发费用", "研发费用、研发投入占营收比例、研发人员"),
        ("销售费用", "销售费用", "市场推广", "销售费用、销售费用率、市场推广费"),
        ("在研管线", "在研", "临床", "在研产品管线、临床阶段、注册阶段、获批上市"),
        ("无形资产", "无形资产", "专利", "无形资产明细、专利、商标、技术许可"),
    ],
    "801790": [  # 非银金融（保险+券商）
        ("保费收入", "保费收入", "保险业务", "保费收入、原保险保费收入、分保费收入"),
        ("赔付支出", "赔付支出", "退保金", "赔付支出、退保金、保险责任准备金"),
        ("投资收益", "投资收益", "投资资产", "投资收益、投资资产配置、总投资收益率"),
        ("偿付能力", "偿付能力", "偿付能力充足率", "偿付能力充足率、核心偿付能力充足率"),
        ("新业务价值", "新业务价值", "内含价值", "新业务价值、内含价值、剩余边际"),
        ("手续费佣金", "手续费及佣金", "佣金", "手续费及佣金收入、手续费及佣金支出"),
    ],
}

# ── Universal sections (shared across all industries) ──
UNIVERSAL_SECTIONS = [
    ("合并资产负债表", "合并资产负债表", "资产负债表所有科目"),
    ("合并利润表", "合并利润表", "利润表所有科目"),
    ("合并现金流量表", "合并现金流量表", "现金流量表所有科目"),
]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate industry-specific rules from real reports.")
    p.add_argument("--industry", help="Filter to one industry")
    p.add_argument("--year", type=int, default=2023, help="Report year")
    p.add_argument("--max-concurrent", type=int, default=5, help="Max concurrent LLM calls")
    p.add_argument("--universal-only", action="store_true", help="Only generate universal rules")
    return p.parse_args(argv)


def _get_report_text(ticker: str, year: int) -> Optional[str]:
    company = cninfo_client.lookup_company(ticker)
    if not company:
        return None
    filings = cninfo_client.query_announcements(
        company["stock_code"], company["org_id"], form="年度报告", year=year, limit=5,
    )
    if not filings:
        return None
    # Prefer full report over summary
    selected = None
    for f in filings:
        if "摘要" not in f.get("title", ""):
            selected = f
            break
    if selected is None:
        selected = filings[0]
    text, info = report_cache.get_or_fetch(
        selected["pdf_url"], stock_code=ticker, year=year,
        form="年度报告", announcement_id=selected["announcement_id"],
    )
    return text if text else None


def _extract_section_text(text: str, keyword: str, min_offset: int = 5000) -> Optional[str]:
    """Extract text around a keyword occurrence in the report."""
    idx = text.find(keyword, min_offset)
    if idx < 0:
        return None
    start = max(0, idx - 200)
    end = min(len(text), idx + 8000)
    return text[start:end]


def _call_llm(system: str, user: str) -> dict:
    """Call LLM and return parsed JSON."""
    cfg = {
        "base_url": os.environ.get("LLM_BASE_URL", "").rstrip("/"),
        "api_key": os.environ.get("LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
    }
    url = cfg["base_url"] + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": 32000,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    for attempt in range(2):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=300.0)
            if resp.status_code == 429:
                time.sleep(10)
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            if attempt == 0:
                time.sleep(3)
    raise RuntimeError("LLM call failed")


def _generate_section_rules(
    section_text: str,
    section_name: str,
    guidance: str,
    document_type: str,
    label: str,
) -> list[dict]:
    """Generate rules for ONE section."""
    system = (
        "You are a financial report analyst. Extract financial indicators from this section "
        "of a Chinese annual report. For each indicator, produce a rule with: "
        "indicator (Chinese name, exact terminology from the report), "
        "instruction (how to extract from this section), "
        "position (the section/title where this indicator appears), "
        f"document_type ('{document_type}'), "
        "module (balance_sheet/income_statement/cashflow/financial_ratio/report_section), "
        "subgroup, unit, period_type (annual). "
        "Return JSON: {\"rules\": [...]}."
    )
    user = (
        f"Document type: {document_type}\n"
        f"Industry: {label}\n"
        f"Section: {section_name}\n"
        f"Focus on: {guidance}\n\n"
        f"Section text:\n{section_text[:12000]}\n\n"
        "Return {\"rules\": [...]}. Only include indicators actually present in this text."
    )
    try:
        result = _call_llm(system, user)
        rules = result.get("rules", [])
        if isinstance(rules, list):
            return rules
        return []
    except Exception as e:
        print(f"    ✗ {section_name}: {e}")
        return []


def _persist_rules(rules: list[dict]) -> int:
    from rules_models import LlmRuleModel
    persisted = 0
    for r in rules:
        try:
            validated = LlmRuleModel.model_validate(r)
            rules_db.upsert_llm_rule(validated.model_dump(exclude_none=False))
            persisted += 1
        except Exception:
            pass
    return persisted


def generate_universal_rules(ticker: str, year: int, document_type: str, label: str, max_workers: int) -> int:
    """Generate universal rules from 三大表 + 主要财务指标."""
    text = _get_report_text(ticker, year)
    if not text:
        return 0

    sections_to_extract = []
    for name, keyword, guidance in UNIVERSAL_SECTIONS:
        st = _extract_section_text(text, keyword)
        if st:
            sections_to_extract.append((st, name, guidance))

    all_rules = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(sections_to_extract))) as executor:
        futures = {
            executor.submit(_generate_section_rules, st, name, guidance, document_type, label): name
            for st, name, guidance in sections_to_extract
        }
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                rules = fut.result()
                if rules:
                    print(f"    ✓ {name:30s} {len(rules)} rules")
                    all_rules.extend(rules)
            except Exception as e:
                print(f"    ✗ {name:30s} {e}")

    seen = {}
    for r in all_rules:
        name = r.get("indicator", "")
        if name and name not in seen:
            seen[name] = r
    rules = list(seen.values())

    persisted = _persist_rules(rules)
    print(f"    Universal: {persisted} rules persisted")
    return persisted


def generate_industry_specific_rules(
    ticker: str, year: int, document_type: str, label: str, sw_code: str, max_workers: int
) -> int:
    """Generate industry-specific rules for this industry."""
    text = _get_report_text(ticker, year)
    if not text:
        return 0

    specs = INDUSTRY_SECTIONS.get(sw_code, [])
    if not specs:
        print(f"    No industry-specific sections defined")
        return 0

    sections_to_extract = []
    for name, keyword, _, guidance in specs:
        st = _extract_section_text(text, keyword)
        if st:
            sections_to_extract.append((st, name, guidance))

    if not sections_to_extract:
        print(f"    No applicable sections found in report")
        return 0

    all_rules = []
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(sections_to_extract)))) as executor:
        futures = {
            executor.submit(_generate_section_rules, st, name, guidance, document_type, label): name
            for st, name, guidance in sections_to_extract
        }
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                rules = fut.result()
                if rules:
                    print(f"    ✓ {name:30s} {len(rules)} rules")
                    all_rules.extend(rules)
            except Exception as e:
                print(f"    ✗ {name:30s} {e}")

    seen = {}
    for r in all_rules:
        name = r.get("indicator", "")
        if name and name not in seen:
            seen[name] = r
    rules = list(seen.values())

    persisted = _persist_rules(rules)
    print(f"    Industry-specific: {persisted} rules persisted")
    return persisted


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.industry:
        industries = {args.industry: REP_COMPANY[args.industry]}
    else:
        industries = REP_COMPANY

    # Step 1: Generate universal rules from 食品饮料
    if "801120" in industries:
        ticker, name, label = industries["801120"]
        dt = f"cn/801120/listed/annual-report"
        print(f"\n{'='*60}")
        print(f"Phase 1: Universal rules from {label} ({name})")
        generate_universal_rules(ticker, args.year, dt, label, args.max_concurrent)

    if args.universal_only:
        return 0

    # Step 2: Generate industry-specific rules for each industry
    for sw_code, (ticker, name, label) in industries.items():
        if sw_code == "801120":
            continue  # already done
        dt = f"cn/{sw_code}/listed/annual-report"
        print(f"\n{'='*60}")
        print(f"Phase 2: {label} ({sw_code}) — {name} ({ticker})")
        generate_industry_specific_rules(ticker, args.year, dt, label, sw_code, args.max_concurrent)

        with rules_db._session() as session:
            total = session.query(LlmRule).filter(LlmRule.document_type == dt).count()
        print(f"  Total in DB: {total} LLM rules")

    print(f"\n{'='*60} Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())