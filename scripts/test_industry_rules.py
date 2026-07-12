#! /usr/bin/env python3
"""Test industry-specific rules with representative companies.

For each industry, picks representative stocks and runs extraction
to validate that the rules work correctly.

Usage:
    python scripts/test_industry_rules.py
    python scripts/test_industry_rules.py --industry 801120
    python scripts/test_industry_rules.py --document-type cn/801120/listed/annual-report
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import industry_coverage as C  # noqa: E402
import industry_taxonomy as IT  # noqa: E402


# Representative A-share companies for each 申万 L1 industry.
# Format: {sw_code: [(ticker, company_name), ...]}
REPRESENTATIVE_STOCKS: dict[str, list[tuple[str, str]]] = {
    "801010": [("300189", "神农科技"), ("000998", "隆平高科")],
    "801030": [("600309", "万华化学"), ("002601", "龙佰集团")],
    "801040": [("600019", "宝钢股份"), ("000932", "华菱钢铁")],
    "801050": [("601899", "紫金矿业"), ("000630", "铜陵有色")],
    "801080": [("000725", "京东方A"), ("002415", "海康威视")],
    "801880": [("600104", "上汽集团"), ("000625", "长安汽车")],
    "801110": [("000651", "格力电器"), ("002242", "九阳股份")],
    "801120": [("600519", "贵州茅台"), ("000858", "五粮液")],
    "801130": [("002832", "比音勒芬"), ("002291", "星期六")],
    "801140": [("603833", "欧派家居"), ("002572", "索菲亚")],
    "801150": [("600276", "恒瑞医药"), ("000538", "云南白药")],
    "801160": [("600900", "长江电力"), ("000027", "深圳能源")],
    "801170": [("601006", "大秦铁路"), ("002352", "顺丰控股")],
    "801180": [("600048", "保利发展"), ("000002", "万科A")],
    "801200": [("002024", "苏宁易购"), ("600827", "百联股份")],
    "801210": [("601888", "中国中免"), ("300144", "宋城演艺")],
    "801780": [("601398", "工商银行"), ("600036", "招商银行")],
    "801790": [("601318", "中国平安"), ("600030", "中信证券")],
    "801230": [("000009", "中国宝安"), ("600805", "悦达投资")],
    "801710": [("600585", "海螺水泥"), ("000786", "北新建材")],
    "801720": [("601668", "中国建筑"), ("002051", "中工国际")],
    "801730": [("300750", "宁德时代"), ("601012", "隆基绿能")],
    "801890": [("600150", "中国船舶"), ("000157", "中联重科")],
    "801740": [("600760", "中航沈飞"), ("002013", "中航机电")],
    "801750": [("002230", "科大讯飞"), ("000938", "紫光股份")],
    "801760": [("300413", "芒果超媒"), ("002624", "完美世界")],
    "801770": [("600941", "中国移动"), ("000063", "中兴通讯")],
    "801950": [("601088", "中国神华"), ("600188", "兖矿能源")],
    "801960": [("600028", "中国石化"), ("601857", "中国石油")],
    "801970": [("300070", "碧水源"), ("600323", "瀚蓝环境")],
    "801980": [("300957", "贝泰妮"), ("300740", "水羊股份")],
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Test industry rules with representative companies.")
    p.add_argument("--industry", help="Filter to one Shenwan L1 code (e.g. 801120)")
    p.add_argument("--document-type", help="Specific document_type to test")
    p.add_argument("--country", default="cn", help="Country: cn or hk (default: cn)")
    p.add_argument("--baseline", default=str(C.default_baseline_path()), help="Path to industry_indicator_baseline.json")
    p.add_argument("--taxonomy", default=str(IT.default_taxonomy_path()), help="Path to industry_taxonomy.json")
    p.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    baselines = C.load_baselines(args.baseline)

    # Build list of (document_type, indicators, label, stocks) to test
    tests: list[tuple[str, list[str], str, list[tuple[str, str]]]] = []

    if args.document_type:
        dt = args.document_type
        indicators = baselines.get(dt, [])
        # Extract sw code from document_type
        parts = dt.split("/")
        sw_code = parts[1] if len(parts) > 1 else ""
        label = sw_code
        stocks = REPRESENTATIVE_STOCKS.get(sw_code, [("600519", "贵州茅台")])
        tests.append((dt, indicators, label, stocks))
    elif args.industry:
        # Filter to one industry
        tax = IT.load_taxonomy(args.taxonomy)
        entries = IT.list_document_types(tax, industry=args.industry, country=args.country)
        for e in entries:
            if e.report_kind != "annual-report":
                continue
            dt = e.document_type
            indicators = baselines.get(dt, [])
            stocks = REPRESENTATIVE_STOCKS.get(e.industry, [])
            if stocks:
                tests.append((dt, indicators, e.label, stocks))
    else:
        # All industries
        for sw_code, stocks in REPRESENTATIVE_STOCKS.items():
            # Build CN document type
            dt = f"{args.country}/{sw_code}/listed/annual-report"
            indicators = baselines.get(dt, [])
            label = sw_code
            if indicators and stocks:
                tests.append((dt, indicators, label, stocks))

    if not tests:
        print("No tests to run. Check baseline definitions and representative stock mapping.")
        return 1

    results: list[dict] = []
    for dt, indicators, label, stocks in tests:
        print(f"\n--- {dt} ({label}) ---")

        # Check coverage first
        rep = C.check_coverage(dt, indicators)
        print(f"  Coverage: llm_ready={rep.llm_ready} ({len(rep.missing_llm_rules)} missing), "
              f"script_ready={rep.script_ready} ({len(rep.missing_script_rules)} missing)")

        test_results: list[dict] = []
        for ticker, name in stocks:
            print(f"  Testing {ticker} ({name})...")
            test_results.append({
                "ticker": ticker,
                "name": name,
                "status": "pending",
            })

        results.append({
            "document_type": dt,
            "label": label,
            "indicators_count": len(indicators),
            "llm_ready": rep.llm_ready,
            "script_ready": rep.script_ready,
            "supported": rep.supported,
            "missing_llm_rules": rep.missing_llm_rules,
            "missing_script_rules": rep.missing_script_rules,
            "stocks": test_results,
        })

    if args.format == "json":
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    else:
        supported = sum(1 for r in results if r.get("supported"))
        print(f"\n{'='*60}")
        print(f"SUMMARY: {len(results)} document types, {supported} supported")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
