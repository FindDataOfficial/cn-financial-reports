# cnreport-mcp

MCP server for Chinese A-share annual reports. Sixteen tools across three layers:

| Layer | Tool | What it does |
|---|---|---|
| Company API (edgartools-style) | `get_company` | Resolve ticker / name → company entry |
| | `list_filings` | List CNINFO disclosures by form / category + year |
| | `get_filing` | One announcement's metadata + PDF URL |
| | `get_financials` | Income / balance / cashflow via akshare (structured numbers) |
| | `get_financial_statements` | 三大报表 (`合并利润表` / `合并资产负债表` / `合并现金流量表`) as **text** from the annual-report PDF via TOC |
| | `get_section` | `(ticker, year, section)` → section text |
| | `list_report_types` | Browse the CNINFO disclosure category catalog |
| | `get_special_report` | Retrieve a special-type report (招股说明书 / 收购报告书 / …) by category |
| PDF / AI / ES | `list_outline` | Parse 目录 from a report URL or PDF path |
| | `extract_section` | Body text by exact title / regex / ordinal |
| | `ai_extract` | LLM-structured extraction over section text |
| | `index_records` | Bulk index extracted records into ES |
| | `search_reports` | BM25 + filter search with highlights |
| | `delete_index` | Drop `cnreport-{year}` index |
| Report cache | `list_cache` | List cached reports (stock / year / form / size / cached_at) |
| | `clear_cache` | Evict cached reports (all / by company / by company+year) |
| Indicators | `list_indicators` | Browse the indicator rule set (by module / query / company applicability) |
| | `get_indicator` | One indicator's value for (indicator, company, period) — routes to akshare / PDF section / computed ratio |
| | `extract_indicators` | All applicable indicators for one company/year in one pass (one fetch, batched LLM, cached bundle) |
| | `extract_indicators_by_position` | Indicators named in a position CSV (`docs/indicators_position.csv`) for one company/year — external/realtime ones listed in `skipped` |

## Typical chain

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

## Special report types

CNINFO exposes dozens of disclosure categories beyond the four periodic reports
(招股说明书, 增发, 业绩预告, 收购报告书, 股权激励, …). Browse the catalog, then list or
retrieve by category:

```python
# 1. Browse what's available → 2. list filings of a category → 3. pull a section

catalog = list_report_types()
# {"groups": [{"name": "定期报告", "categories": [...]}, {"name": "融资", ...}, ...], "count": 26}

list_report_types(group="融资")
# {"group": "融资", "categories": [{name: "首发", code: "category_sf_szsh", ...}, ...], "count": 6}

filings = list_filings("600519", category="首发", limit=3)   # 首发 covers 招股说明书
# category accepts a catalog name OR a raw category_* code; mutually exclusive with form.

sec = get_special_report("600519", category="首发", section="募集资金运用")
# {"text": "<section body>", "pdf_url": "...", "outline_entry": {...}, ...}

# Without `section`, the PDF is NOT downloaded — only filing metadata + pdf_url:
meta = get_special_report("600519", category="业绩预告")
```

## Three major financial statements (三大报表)

`get_financials` returns akshare's structured numeric tables. `get_financial_statements`
pulls the three major statement sections **as text straight from the annual-report
PDF** (via the table of contents), so you get the report's actual narrative + tables,
not just the numbers:

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

# Consolidated (合并) titles are preferred; the un-prefixed titles are the
# fallback. Any statement not located in the TOC is listed in `missing`, with
# the full `available` title list so you can fall back to get_section:
stmts = get_financial_statements("600519", year=2023)
# {"missing": ["cashflow"], "available": ["第一节 ...", ...], ...}
```

## Report cache

Every report fetch (`list_outline`, `extract_section`, `get_section`,
`get_special_report`, `get_financial_statements`) goes through an on-disk cache:
the first fetch downloads the PDF + extracts text + outline and stores them
under `mcp/cnreport-mcp/.cache/reports/`; subsequent fetches of the **same**
report read from disk — no re-download, no re-`pypdf`-parse. Files are named
`{stock_code}_{year}_{form}_{announcement_id}.{pdf,txt,outline.json}` (or
`url_<hash>.*` for raw URL fetches without provenance), so the cache folder is
human-browseable.

```python
list_cache()
# {"cache_dir": ".../.cache/reports", "count": 2,
#  "entries": [{"stock_code": "600519", "year": "2023", "form": "年度报告",
#               "announcement_id": "1219730876", "cached_at": "...", "size": 123456}, ...]}

clear_cache()                              # evict everything
clear_cache(stock_code="600519")           # evict one company
clear_cache(stock_code="600519", year=2023) # evict one company + year
```

Override the cache directory with `CNREPORT_CACHE_DIR` (see Configuration).
CNINFO annual reports are immutable post-publication, so there is no TTL —
`clear_cache` is the manual eviction path.

The category catalog is the data-driven file `cninfo_categories.json` (sourced from
CNINFO's own `history-notice.js` via akshare). **Adding a report type = editing that
JSON** — no code change. Restart the server and the new type appears in
`list_report_types` and is accepted by `list_filings(category=…)` / `get_special_report(…)`.

Skip the company API and pass a PDF URL directly when you already have one:

```python
list_outline(source="https://example.com/600519_2023.pdf")
extract_section(source="...", selector="管理层讨论与分析", company="贵州茅台", year=2023)
```

## Indicators

`indicator_rules.json` is a data-driven rule set mapping each indicator to
**where** its value comes from and **how** it is extracted. Each rule carries:
applicability (`applies_to`: industry / sub-type / explicit company list), a
section selector chain, an extractor (`"llm"` or `"python:<name>"`), and
unit/period. The rule set has two sources, both edited without a code change:

- **Banking rules** — hand-authored in `indicator_rules.json` (sourced from
  `indicators.md`); carry rich, bank-specific selector chains + applicability.
- **Position-CSV rules** — migrated from `docs/indicators_position.csv` (319
  indicators across the three statements, notes, risk management, shareholders,
  HR, profit distribution, …) by `scripts/migrate_indicators_csv.py`. Edit the
  CSV, re-run the migration, done. Indicators marked `report_type: 实时`
  (PE-TTM, PB, 市值, …) are classified `source_type: "external"` — they are not
  in the report PDF and are listed in `skipped` during extraction.

`docs/indicators-methodology.md` is the rendered source-and-process companion
(regenerate with `python indicators_client.py --render-methodology >
docs/indicators-methodology.md`; coverage summary with `--render-coverage`).

Different banks disclose the same indicator under different TOC titles, and some
indicators only appear for certain bank types — so the engine profiles each
company (国有大行 / 股份制 / 城商行 / 农商行; non-banks profile without a
sub_type and still receive universal `industry: "*"` rules), filters the rule
set per company, and walks the selector chain (company-specific override →
default → fallback, with normalized matching for descriptive section labels).
Derived ratios are computed locally, never by the LLM.

```python
# 1. Preview which indicators apply to a company → 2. pull one → 3. pull all → 4. by CSV
list_indicators(company="工商银行")           # rules applicable to 工商银行 + its profile
get_indicator("资本充足率", "工商银行", 2023)  # one value, routed per the rule
extract_indicators("工商银行", 2023)           # all applicable indicators, one PDF fetch
extract_indicators("工商银行", 2023,
                   indicators=["资本充足率","不良率","资产负债率"])  # subset
extract_indicators("工商银行", 2023, extractor_mode="python")        # LLM-free where possible
extract_indicators_by_position("工商银行", 2023)   # all indicators named in the position CSV
extract_indicators_by_position("工商银行", 2023,
                               csv_path="docs/indicators_position.csv",  # default
                               indicators=["资产总计","负债合计"],         # subset (intersect CSV)
                               extractor="python")                       # LLM-free where possible
```

Each periodic form is selectable via `form` (default `年度报告`):
`半年度报告` / `第一季度报告` / `第三季度报告`. Indicators whose `report_type`
doesn't include the form are placed in `skipped` (e.g. `分红金额` — annual only —
is skipped for `第一季度报告`), and quarterly reports fall back to a body-text
statement search when the outline lacks statement titles.

```python
extract_indicators_by_position("工商银行", 2023, form="第一季度报告")
extract_indicators("贵州茅台", 2023, form="半年度报告")
```

Standalone CLIs run the same pipelines offline — point `--rules` (or `--csv`)
at a different file per company batch to process different companies with
different rule sets:

```bash
# hand-authored + CSV-merged rule set (full engine)
python scripts/extract_indicators.py 601398 --year 2023 \
    [--rules indicator_rules.json] [--extractor auto|llm|python] \
    [--indicators 资本充足率,不良率] [--out-dir ./out]

# position-CSV-driven: the indicators named in a CSV for one company/year/form
python scripts/extract_indicators_by_position.py 601398 --year 2023 \
    [--csv docs/indicators_position.csv] [--extractor auto|llm|python] \
    [--form 年度报告|半年度报告|第一季度报告|第三季度报告] \
    [--indicators 资产总计,负债合计] [--out-dir ./out]
# non-default form is appended to the output stem (e.g. 601398_2023_第一季度报告.json)

# sync docs/indicators_position.csv → indicator_rules.json (idempotent)
python scripts/migrate_indicators_csv.py [--check]
```

Adding a new Python extractor: write `(section_text, rule, period) -> {value, unit, note}`
in `indicators_extractors.py`, call `register("name", fn)`, then set
`"extractor": "python:name"` on the rule. See `docs/indicators-methodology.md`.

### Section cache (LLM response reuse)

The LLM extractor persists the raw `{records:[...]}` response to
`<CNREPORT_CACHE_DIR>/llm_sections/<key>.json`, keyed by
`(pdf_url, section_key, period, rules_hash)`. Once a section has been
extracted, subsequent runs — including single-indicator lookups via
`get_indicator` and re-runs with different indicator subsets — reuse the
cached records and only re-query the LLM for indicators not yet cached.

The bundle exposes a `section_cache_reuse: <int>` field that counts records
served from the section cache in that run (distinct from `cached: true`,
which indicates a full bundle hit). Set `LLM_SECTION_CACHE=off` to disable
the cache at runtime. The cache is on by default; safe to leave on
indefinitely because CNINFO reports are immutable.

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

Tests (offline; bypasses the user's broken logfire pytest plugin):

```bash
uv run --with pytest python -m pytest test_cnreport.py -v -p no:logfire
```

## Configuration

CNINFO and akshare are **keyless**. The other tools need env vars in root `.env`:

| Var | Used by | Required? |
|---|---|---|
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | `ai_extract` | Yes for AI |
| `ES_URL` (+ optional `ES_API_KEY` or `ES_USERNAME`/`ES_PASSWORD`) | `index_records`, `search_reports`, `delete_index` | Yes for ES |
| `DAAS_DATABASE_URL` | provenance writes for `extract_section` | Defaults to `mcp/daas.db` |
| `CNREPORT_CACHE_DIR` | report cache for all fetch paths | Defaults to `mcp/cnreport-mcp/.cache/reports/` |

## Architecture

- `cninfo_client.py` — single network entry point for CNINFO (`lookup_company`, `query_announcements`, `get_announcement`, `pdf_url`). Three keyless endpoints. Also loads the data-driven category registry (`load_categories`, `resolve_category`).
- `cninfo_categories.json` — CNINFO disclosure category catalog (name → code, grouped). Source of truth for `list_report_types` and the `category` parameter; extensible by JSON edit.
- `financials_client.py` — lazy-imports akshare; server boots even without it (`get_financials` returns an `{error}` instead).
- `cnreport_tools.py` — pure helpers + the company-API wrappers (`list_report_types`, `get_special_report`, `get_financial_statements`). Errors return `{"error": ...}`, never raise.
- `report_cache.py` — on-disk cache wrapping `fetch_source_with_bytes`; every fetch path (`list_outline`, `extract_section`, `get_section`, `get_special_report`, `get_financial_statements`) checks the cache before downloading and stores the PDF + extracted text + outline on a miss. `list_cache` / `clear_cache` manage it. Also persists the extracted indicator bundle (`{stem}.indicators.json`) used by `extract_indicators`.
- `indicators_client.py` — indicator rules engine: loads `indicator_rules.json`, profiles a company, filters applicable rules, routes each to akshare / report-section / computed / external, dispatches LLM or Python extractors, evaluates ratio formulas, and renders the methodology + coverage docs. Also exposes `extract_indicators_by_position` (CSV-driven).
- `indicators_extractors.py` — pluggable Python extractor registry (`register` / `get`) + starter extractors (`regex_amount`, `percent_value`, `table_row`, `headcount`). Add an extractor = add a function + `register`.
- `indicator_rules.json` — data-driven indicator rule set (name → applicability + section selector chain + extractor + unit + source_type). Hand-authored banking rules + CSV-migrated rules from `docs/indicators_position.csv`. Source of truth for `list_indicators` / `get_indicator` / `extract_indicators` / `extract_indicators_by_position`; extensible by JSON edit.
- `indicators_csv_migration.py` — converts `docs/indicators_position.csv` into `indicator_rules.json` rules (idempotent; appends CSV-only rules, annotates overlaps, preserves hand-authored rules). Run via `scripts/migrate_indicators_csv.py`.
- `docs/indicators_position.csv` — maintained human-editable catalog of indicators → section / report_type. The source for CSV-migrated rules.
- `scripts/extract_indicators.py` — standalone CLI that runs the engine for a company or list, with a selectable rule file (`--rules`) and extractor mode (`--extractor`), writing JSON + CSV.
- `scripts/extract_indicators_by_position.py` — standalone CLI that extracts the indicators named in a position CSV (`--csv`) for a company/year, writing JSON + CSV (with a `status` column and `skipped` rows for external indicators).
- `scripts/migrate_indicators_csv.py` — CLI wrapper around `indicators_csv_migration.migrate` (`--check` for a dry-run diff).
- `server.py` — `@app.tool` registrations; thin pass-through to `cnreport_tools` / `report_cache` / `indicators_client`.
