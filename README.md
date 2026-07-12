# cnreport-mcp

MCP server for Chinese financial reports — 31 申万 L1 industry AI rule system,
outline extraction, AI structured extraction, Elasticsearch store + search,
and interactive rules dashboard.

## Industry Rules System

**21,698 LLM rules** covering **31 申万 L1 industries** with per-section extraction
instructions generated from real annual report PDFs. Each rule maps an indicator
to its exact section position in the periodic report.

### Coverage

| 章节 | 内容 | 说明 |
|------|------|------|
| 资产负债表 | 全部科目 (112+ rules) | 从合并资产负债表提取 |
| 利润表 | 全部科目 (130+ rules) | 从合并利润表提取 |
| 现金流量表 | 全部科目 (42+ rules) | 从合并现金流量表提取 |
| 管理层讨论 | 主营业务分析、成本、产销量、研发 | 从实际报告第三节提取 |
| 主要财务指标 | ROE、EPS、毛利率、分季度数据 | 从第二节提取 |
| 报表附注/重要事项 | 关联交易、担保、诉讼、资产减值 | 从第六节+第十节附注提取 |
| 股东信息 | 前十大股东、持股变动、分红 | 从第七节提取 |
| 公司治理 | 董事会、高管薪酬 | 从第四节提取 |
| 环境 | 排污、碳排放、能源消耗 | 从第五节提取 |

### Industry-Specific Rules

6 industries have industry-specific rules on top of the universal set:

| 行业 | 特有指标 | 来源 |
|------|---------|------|
| 银行 | 不良率、净息差、资本充足率、贷款五级分类 | 工商银行年报 |
| 房地产 | 合同负债、存货-开发成本、土储、销售面积 | 保利发展年报 |
| 电力设备 | 在建工程、产能利用率、应收账款 | 宁德时代年报 |
| 医药生物 | 研发费用、销售费用、在研管线、无形资产 | 恒瑞医药年报 |
| 非银金融 | 保费收入、赔付支出、偿付能力、新业务价值 | 中国平安年报 |
| 农林牧渔 | 存货-消耗性生物资产 | 隆平高科年报 |

### Rule Generation Pipeline

Rules are generated from real annual report PDFs via parallel LLM calls:

```bash
# Generate rules for all 31 industries from real reports
python scripts/generate_rules_from_real_reports.py --max-concurrent 5

# Single industry
python scripts/generate_rules_from_real_reports.py --industry 801120

# Run industry-specific sections only
python scripts/generate_rules_from_real_reports.py --industry 801780 --llm-only
```

### Dashboard

Interactive web UI to browse, filter, and search all 21,698 rules:

```bash
# CLI
python scripts/industry_rules_dashboard.py
# or
cnreport-dashboard

# MCP tool
open_industry_rules_dashboard(port=8888)
```

Features:
- **Industry filter** — dropdown with all 31 申万 L1 industries
- **Module filter** — filter by balance_sheet, income_statement, etc.
- **Keyword search** — indicator name, section, instruction text
- **Sortable columns** — click header to sort
- **Pagination** — 50 rules per page
- **Color-coded tags** — module type visualization
- **Real-time stats** — filtered count, industry count, module count

---

## Tools (26 MCP tools)

| Layer | Tool | Description |
|-------|------|-------------|
| **Company API** | `get_company` | Resolve ticker/name → company entry |
| | `list_filings` | List CNINFO disclosures by form/category + year |
| | `get_filing` | One announcement's metadata + PDF URL |
| | `get_financials` | Income/balance/cashflow via akshare |
| | `get_financial_statements` | 三大报表 as text from the annual-report PDF |
| | `get_section` | `(ticker, year, section)` → section text |
| | `list_report_types` | Browse CNINFO disclosure category catalog |
| | `get_special_report` | Special-type report (招股说明书, 收购报告书, …) |
| **HK Stock** | `get_hk_company` | Resolve HK stock by ticker/name |
| | `list_hk_filings` | List HKEX filings |
| | `get_hk_financials` | HK financial statements |
| | `get_hk_section` | HK report section extraction |
| **PDF / AI / ES** | `list_outline` | Parse 目录 from report URL or PDF path |
| | `extract_section` | Body text by exact title / regex / ordinal |
| | `ai_extract` | LLM-structured extraction over section text |
| | `index_records` | Bulk index records into ES |
| | `search_reports` | BM25 + filter search with highlights |
| | `delete_index` | Drop `cnreport-{year}` index |
| **Cache** | `list_cache` | List cached reports |
| | `clear_cache` | Evict cached reports |
| **Indicators** | `list_indicators` | Browse indicator rule set |
| | `get_indicator` | One indicator's value |
| | `extract_indicators` | All applicable indicators in one pass |
| | `extract_indicators_by_position` | CSV-driven extraction |
| | `extract_indicators_batch` | Batch concurrent extraction |
| **Dashboard** | `open_industry_rules_dashboard` | Start the rules web dashboard |

## Typical Chain

```python
# 1. Resolve company → 2. find latest annual → 3. pull MD&A → 4. LLM-extract revenue table

co = get_company("600519")
# {"stock_code": "600519", "name": "贵州茅台", "org_id": "gssh0600519", "exchange": "sse", ...}

filings = list_filings("600519", form="年度报告", year=2023, limit=3)
# [{"announcement_id": "1219730876", "pdf_url": "http://static.cninfo.com.cn/.../*.PDF", ...}]

sec = get_section("600519", year=2023, section="管理层讨论与分析")
# {"text": "<full MD&A body>", "pdf_url": "...", "outline_entry": {...}, ...}

records = ai_extract(
    text=sec["text"],
    schema={"type": "object", "properties": {
        "segment": {"type": "string"},
        "revenue_2023": {"type": "string"},
    }, "required": ["segment", "revenue_2023"]},
)
# {"records": [{"segment": "茅台酒", "revenue_2023": "139,989,000,000"}, ...]}
```

## Special Report Types

CNINFO exposes dozens of disclosure categories beyond the four periodic reports
(招股说明书, 增发, 业绩预告, 收购报告书, 股权激励, …). Browse the catalog, then list or
retrieve by category:

```python
catalog = list_report_types()
# {"groups": [{"name": "定期报告", "categories": [...]}, {"name": "融资", ...}, ...], "count": 26}

list_report_types(group="融资")
# {"group": "融资", "categories": [{name: "首发", code: "category_sf_szsh", ...}, ...], "count": 6}

filings = list_filings("600519", category="首发", limit=3)

sec = get_special_report("600519", category="首发", section="募集资金运用")
```

## 三大报表 (Three Major Financial Statements)

`get_financials` returns akshare's structured numeric tables. `get_financial_statements`
pulls the three major statement sections **as text** from the PDF:

```python
stmts = get_financial_statements("600519", year=2023)
# {
#   "stock_code": "600519", "company_name": "贵州茅台", "year": 2023,
#   "form": "年度报告", "pdf_url": "...", "cached": False,
#   "statements": {
#     "income_statement": {"title": "2、 合并利润表", "outline_entry": {...}, "char_count": 4521, "text": "..."},
#     "balance_sheet":    {"title": "1、 合并资产负债表", ...},
#     "cashflow":         {"title": "3、 合并现金流量表", ...},
#   },
#   "missing": [],
# }
```

## Report Cache

Every report fetch goes through an on-disk cache under `.cache/reports/`.
First fetch downloads PDF + extracts text + outline; subsequent fetches read from disk.

```python
list_cache()
# {"cache_dir": ".../.cache/reports", "count": 2, "entries": [...]}

clear_cache()                              # evict everything
clear_cache(stock_code="600519")           # evict one company
clear_cache(stock_code="600519", year=2023) # evict one company + year
```

## Indicators

The indicator engine profiles each company, filters applicable rules, and
routes each indicator to akshare / report-section / computed / external.

```python
# Preview → pull one → pull all → CSV
list_indicators(company="工商银行")           # rules applicable to 工商银行
get_indicator("资本充足率", "工商银行", 2023)  # one value
extract_indicators("工商银行", 2023)           # all applicable, one PDF fetch
extract_indicators("工商银行", 2023,
                   indicators=["资本充足率","不良率"])  # subset
extract_indicators("工商银行", 2023, extractor_mode="python")  # LLM-free
extract_indicators_by_position("工商银行", 2023)  # CSV-driven
```

Multi-form support (年度报告 / 半年度报告 / 第一季度报告 / 第三季度报告):

```python
extract_indicators_by_position("工商银行", 2023, form="第一季度报告")
extract_indicators("贵州茅台", 2023, form="半年度报告")
```

### Concurrency

```python
extract_indicators("工商银行", 2023, concurrency=4)  # explicit cap
extract_indicators("工商银行", 2023, concurrency=1)  # sequential

# Batch: multi-company concurrent extraction
extract_indicators_batch([("601398", 2023), ("600519", 2023)],
                         concurrency=2, extract_concurrency=4)
# → {"results": {"601398_2023": {...}, ...}, "failures": [...], "concurrency": 2}
```

### Section Cache

LLM responses are persisted to disk, keyed by `(pdf_url, section_key, period, rules_hash)`.
Subsequent runs reuse cached records. Set `LLM_SECTION_CACHE=off` to disable.

## Standalone CLIs

```bash
# Full engine extraction
python scripts/extract_indicators.py 601398 --year 2023 \
    [--rules indicator_rules.json] [--extractor auto|llm|python] \
    [--indicators 资本充足率,不良率] [--out-dir ./out]

# CSV-driven extraction
python scripts/extract_indicators_by_position.py 601398 --year 2023 \
    [--csv docs/indicators_position.csv] [--extractor auto|llm|python] \
    [--form 年度报告|半年度报告|第一季度报告|第三季度报告]

# Multi-year extraction
python scripts/extract_indicators_multiyear.py 601398 2023 2024

# Industry rules dashboard
python scripts/industry_rules_dashboard.py [port]
# or: cnreport-dashboard

# Generate industry rules from real reports
python scripts/generate_rules_from_real_reports.py

# Check industry coverage
python scripts/check_industry_coverage.py

# Seed industry rules
python scripts/seed_industry_rules.py
```

## HK Stock Support

```python
get_hk_company("00700")                    # → 腾讯控股
list_hk_filings("00700", year=2023)        # → HKEX filings
get_hk_financials("00700")                 # → financial statements
get_hk_section("00700", year=2023, section="管理层讨论与分析")
```

## Setup

```bash
uv sync                    # installs akshare, pypdf, fastmcp, ...
uv run python server.py    # FastMCP over stdio
```

Self-check (no network):

```bash
uv run python selfcheck.py           # DB + outline + company API + special reports
uv run python selfcheck_cache.py     # report cache + three-statements extraction
```

Tests (offline):

```bash
uv run --with pytest python -m pytest test_cnreport.py -v -p no:logfire
```

## Configuration

CNINFO and akshare are **keyless**. Other tools need env vars in `.env`:

| Var | Used by | Required? |
|-----|---------|-----------|
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | `ai_extract`, rule generation | Yes for AI |
| `ES_URL` (+ optional `ES_API_KEY` or `ES_USERNAME`/`ES_PASSWORD`) | `index_records`, `search_reports`, `delete_index` | Yes for ES |
| `DAAS_DATABASE_URL` | provenance writes, rules storage | Defaults to `daas.db` |
| `CNREPORT_CACHE_DIR` | report cache | Defaults to `.cache/reports/` |

## Architecture

```
cnreport/
├── server.py                      # FastMCP server (@app.tool registrations)
├── cninfo_client.py               # CNINFO API (keyless lookup + query)
├── hk_stock_client.py             # HK stock API (akshare + HKEX)
├── financials_client.py           # akshare financial statements (lazy)
├── cnreport_tools.py              # Pure helpers (outline, extract, LLM, ES)
├── report_cache.py                # On-disk PDF + text + outline cache
├── llm_section_cache.py           # LLM response section cache
│
├── indicators_client.py           # Rules engine (load, profile, route, extract)
├── indicators_extractors.py       # Pluggable Python extractors
├── indicators_models.py           # Pydantic extraction models
├── indicators_csv_migration.py    # CSV → JSON rule migration
├── report_section_map.py          # Section alias expansion + matching
│
├── rules_db.py                    # Rules database (SQLite via SQLAlchemy)
├── rules_models.py                # Pydantic rule models
├── rules_skills.py                # LLM rule generation + validation
├── cnreport_models.py             # ORM models (LlmRule, ScriptRule)
├── cnreport_database.py           # Database connection management
│
├── industry_taxonomy.py           # 申万 L1 industry taxonomy
├── industry_coverage.py           # Coverage checks for industry rules
│
├── docs/
│   ├── industry_taxonomy.json     # 31 industry taxonomy
│   ├── industry_indicator_baseline.json  # Baseline indicators per industry
│   ├── indicators_position.csv    # Indicator catalog (CSV source)
│   └── indicators-methodology.md  # Rendered methodology
│
├── scripts/
│   ├── industry_rules_dashboard.py          # Web dashboard (CLI + MCP)
│   ├── generate_rules_from_real_reports.py  # Per-industry rule generation
│   ├── generate_all_industry_rules.py       # LLM rule generation
│   ├── seed_industry_rules.py               # Universal rule seeding
│   ├── seed_missing_industry_rules.py       # Industry-specific seeding
│   ├── extract_indicators.py                # Standalone extraction CLI
│   ├── extract_indicators_by_position.py    # CSV-driven extraction CLI
│   ├── extract_indicators_multiyear.py      # Multi-year batch extraction
│   ├── check_industry_coverage.py           # Coverage validation
│   ├── migrate_indicators_csv.py            # CSV → DB migration
│   └── rules_dashboard.py                   # indicator_rules.json editor
│
└── .cache/reports/                # Downloaded PDFs + extracted text + outlines
```

## Adding a New Industry

1. Add to `docs/industry_taxonomy.json`:
   ```json
   {"industry": "801xxx", "label": "行业名称", "report_kinds": ["annual-report", "interim-report", "quarterly-report"]}
   ```

2. Add baseline indicators to `docs/industry_indicator_baseline.json`:
   ```json
   {"cn/801xxx/listed/annual-report": ["资产总计", "营业收入", "净利润", ...]}
   ```

3. Add representative company to `scripts/generate_rules_from_real_reports.py`:
   ```python
   "801xxx": ("600xxx", "代表公司", "行业名称"),
   ```

4. Define industry-specific sections:
   ```python
   "801xxx": [("section_name", "keyword", "keyword2", "guidance"), ...],
   ```

5. Generate rules:
   ```bash
   python scripts/generate_rules_from_real_reports.py --industry 801xxx
   ```

## License

MIT