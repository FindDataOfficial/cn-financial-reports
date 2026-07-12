#! /usr/bin/env python3
"""Seed missing industry-specific rules for bank, real estate, and financial services.

The universal rules cover the three major statements but miss some
industry-specific indicators that only apply to certain sectors.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import rules_db
from cnreport_models import LlmRule, ScriptRule


CN_LLM = {
    # ── 房地产 (801180) ──
    "cn/801180/listed/annual-report": [
        {
            "indicator": "合同负债",
            "module": "balance_sheet",
            "subgroup": "负债",
            "unit": "元",
            "instruction": "从资产负债表的负债部分找到合同负债金额, 房地产开发企业预收的房款通常在此科目",
            "position": '["合并资产负债表"]',
        },
        {
            "indicator": "预收款项",
            "module": "balance_sheet",
            "subgroup": "负债",
            "unit": "元",
            "instruction": "从资产负债表的负债部分找到预收款项/预收账款金额",
            "position": '["合并资产负债表"]',
        },
    ],
    # ── 银行 (801780) ──
    "cn/801780/listed/annual-report": [
        {
            "indicator": "不良率",
            "module": "report_section",
            "subgroup": "贷款质量",
            "unit": "%",
            "instruction": "从银行年报的贷款质量部分找到不良贷款率, 计算: 不良贷款余额 / 贷款和垫款总额 * 100%",
            "position": '["贷款质量", "信贷质量", "风险分析"]',
        },
        {
            "indicator": "资本充足率",
            "module": "report_section",
            "subgroup": "资本充足率",
            "unit": "%",
            "instruction": "从银行年报的资本充足率部分找到资本充足率(CAR)数值",
            "position": '["资本充足率", "资本管理"]',
        },
        {
            "indicator": "净息差",
            "module": "report_section",
            "subgroup": "净息差",
            "unit": "%",
            "instruction": "从银行年报的财务指标部分找到净息差(NIM)数值",
            "position": '["净息差", "主要财务指标", "财务摘要"]',
        },
        {
            "indicator": "拨备覆盖率",
            "module": "report_section",
            "subgroup": "贷款质量",
            "unit": "%",
            "instruction": "从银行年报的贷款质量部分找到拨备覆盖率(不良贷款拨备覆盖率)",
            "position": '["贷款质量", "信贷质量", "拨备"]',
        },
    ],
    # ── 非银金融 (801790) ──
    "cn/801790/listed/annual-report": [
        {
            "indicator": "营业支出",
            "module": "income_statement",
            "subgroup": "营业支出",
            "unit": "元",
            "instruction": "从利润表找到营业支出合计/营业总支出金额",
            "position": '["合并利润表"]',
        },
        {
            "indicator": "手续费及佣金净收入",
            "module": "income_statement",
            "subgroup": "手续费及佣金",
            "unit": "元",
            "instruction": "从利润表找到手续费及佣金净收入金额, 券商和保险公司的核心收入指标",
            "position": '["合并利润表"]',
        },
        {
            "indicator": "信用减值损失",
            "module": "income_statement",
            "subgroup": "信用减值",
            "unit": "元",
            "instruction": "从利润表找到信用减值损失金额",
            "position": '["合并利润表"]',
        },
    ],
}

HK_LLM = {
    # ── 非银金融 HK (801790) ──
    "hk/801790/listed/annual-report": [
        {
            "indicator": "营业支出",
            "module": "income_statement",
            "subgroup": "营业支出",
            "unit": "元",
            "instruction": "从利润表找到营业支出合计/营业总支出金额",
            "position": '["合并利润表"]',
        },
    ],
}


def _variant_dts(dt: str) -> list[str]:
    """Return the base document type plus interim/quarterly variants."""
    variants = [dt]
    if "/annual-report" in dt:
        variants.append(dt.replace("/annual-report", "/interim-report"))
        variants.append(dt.replace("/annual-report", "/quarterly-report"))
    return variants

def _upsert_rules(dt_rules: dict[str, list[dict]]):
    for dt, rules in dt_rules.items():
        for variant_dt in _variant_dts(dt):
            for r in rules:
                try:
                    rules_db.upsert_llm_rule({
                        "indicator": r["indicator"],
                        "document_type": variant_dt,
                        "module": r["module"],
                        "subgroup": r["subgroup"],
                        "unit": r.get("unit", ""),
                        "instruction": r["instruction"],
                        "position": r["position"],
                        "source_type": "report",
                        "extractor": "llm",
                        "applies_to": {"industry": "*"},
                        "period_type": "annual",
                    })
                    # Also upsert script rule if applicable
                    if r["unit"] == "%":
                        rules_db.upsert_script_rule({
                            "indicator": r["indicator"],
                            "document_type": variant_dt,
                            "extract_rule": "percent_value",
                            "position": r["position"],
                            "module": r["module"],
                            "source_type": "report",
                        })
                    else:
                        rules_db.upsert_script_rule({
                            "indicator": r["indicator"],
                            "document_type": variant_dt,
                            "extract_rule": "regex_amount",
                            "position": r["position"],
                            "module": r["module"],
                            "source_type": "report",
                        })
                    print(f"  ✓ {variant_dt}: {r['indicator']}")
                except Exception as e:
                    print(f"  ✗ {variant_dt}: {r['indicator']} - {e}")


def main() -> int:
    print("Seeding missing industry-specific LLM and script rules...")
    _upsert_rules(CN_LLM)
    _upsert_rules(HK_LLM)
    rules_db.invalidate_rules_cache()
    print("\nDone. Missing rules seeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
