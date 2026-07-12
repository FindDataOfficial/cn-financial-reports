"""
MCP Server for cnreport-mcp — Chinese annual report extraction + AI processing
+ Elasticsearch store/search.

Tools:
  list_outline     — fetch a report and return its 目录 outline
  extract_section  — extract one section's body text by selector
  ai_extract       — LLM structured extraction over section text
  index_records    — bulk-index records into cnreport-{year}
  search_reports   — full-text + filtered search over indexed content
  delete_index     — drop a cnreport-{year} index

Entry: python3 server.py  (FastMCP, stdio transport)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Unified env: root .env first, then per-MCP .env with override=True
try:
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parents[2]  # repo root
    load_dotenv(_ROOT / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
except ImportError:
    pass

# make mcp/models importable
_MODELS = Path(__file__).resolve().parent.parent / "models"
if str(_MODELS) not in sys.path:
    sys.path.insert(0, str(_MODELS))

from fastmcp import FastMCP  # noqa: E402

import cnreport_tools as T  # noqa: E402
from cnreport_database import get_db, make_report_id  # noqa: E402

logger = logging.getLogger("cnreport-mcp")
app = FastMCP(name="cnreport-mcp")

_DEFAULT_MAX_CHARS = 12000
_MAX_SIZE = 50


# ── outline extraction tools ────────────────────────────────────


@app.tool
def list_outline(source: str, fetcher: str = "uv") -> dict:
    """Fetch a Chinese annual report and return its 目录 outline.

    Args:
        source: report URL or local file path (.html/.pdf/.txt).
        fetcher: reserved (v1 uses httpx/pypdf); default "uv".
    """
    import report_cache

    try:
        text, _ = report_cache.get_or_fetch(source, fetcher)
    except Exception as e:
        return {"error": f"fetch failed: {type(e).__name__}: {e}"}
    outline = T.parse_outline(text)
    return {"source": source, "char_count": len(text), "sections": outline}


@app.tool
def extract_section(
    source: str,
    selector: str,
    company: Optional[str] = None,
    stock_code: Optional[str] = None,
    year: Optional[int] = None,
    fetcher: str = "uv",
) -> dict:
    """Extract one section's body text by selector.

    Args:
        source: report URL or local file path.
        selector: exact section title, regex, or 1-based ordinal.
        company/stock_code/year: optional provenance metadata, persisted with the report.
        fetcher: reserved (v1 uses httpx/pypdf).
    """
    import report_cache

    try:
        text, _ = report_cache.get_or_fetch(source, fetcher)
    except Exception as e:
        return {"error": f"fetch failed: {type(e).__name__}: {e}"}
    outline = T.parse_outline(text)
    entry = T.resolve_selector(outline, selector)
    if entry is None:
        return {
            "error": "no section matched selector",
            "available": [e["title"] for e in outline],
        }
    body = T.extract_section_text(text, outline, entry)

    report_id = make_report_id(source, company, year)
    db = get_db()
    db.upsert_document(report_id, source, company, stock_code, year, parse_status="ok")
    db.upsert_section(report_id, entry["ordinal"], entry["level"], entry["title"], len(body))

    return {
        "report_id": report_id,
        "section": entry,
        "char_count": len(body),
        "text": body,
    }


# ── AI processing tool ──────────────────────────────────────────


@app.tool
def ai_extract(
    text: str,
    schema: dict,
    prompt: Optional[str] = None,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> dict:
    """Run LLM structured extraction over report section text.

    Args:
        text: section body text.
        schema: JSON Schema the output must conform to (a record or array of records).
        prompt: optional extra instructions.
        max_chars: truncate input to this many chars (default 12000).
    """
    cfg = T.llm_config()
    if not cfg["api_key"]:
        return {"error": "LLM_API_KEY is not configured"}

    truncated = len(text) > max_chars
    snippet = text[:max_chars]
    system = (
        "You extract structured data from Chinese annual report text. "
        "Return ONLY a JSON object with a 'records' array matching the given schema. "
        "Do not include any prose."
    )
    if prompt:
        system += f" {prompt}"
    user = json.dumps({"schema": schema, "text": snippet}, ensure_ascii=False)

    def _attempt(extra: str = "") -> tuple[Optional[list], Optional[str]]:
        try:
            content = T.call_llm_json(system + extra, user)
            data = json.loads(content)
            records = data.get("records") if isinstance(data, dict) else data
            if not isinstance(records, list):
                return None, "model did not return a records array"
            err = T.validate_against_schema(records, _array_schema(schema))
            if err:
                return None, err
            return records, None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    records, err = _attempt()
    if records is None and err is not None:
        records, err = _attempt(" Your previous output was invalid; fix it and return strict JSON conforming to the schema.")
    if records is None:
        return {"error": "extraction failed", "detail": err, "truncated": truncated}

    return {"records": records, "count": len(records), "truncated": truncated}


def _array_schema(item_schema: dict) -> dict:
    """Wrap a record schema into an array schema for validation."""
    return {"type": "array", "items": item_schema}


# ── Elasticsearch store tool ────────────────────────────────────


@app.tool
def index_records(
    records: list,
    year: int,
    report_id: str,
    section_id: str,
    company: Optional[str] = None,
    stock_code: Optional[str] = None,
    section: Optional[str] = None,
) -> dict:
    """Bulk-index extracted records into cnreport-{year}.

    Args:
        records: list of record dicts (e.g. from ai_extract).
        year: report year → determines the index name.
        report_id/section_id: provenance; form the document _id.
        company/stock_code/section: optional filters stored on each doc.
    """
    try:
        es = T.es_client()
    except Exception as e:
        return {"error": f"ES unavailable: {e}"}

    try:
        name, mapping = T.ensure_index(es, year)
    except Exception as e:
        return {"error": f"index create failed: {e}"}

    now = datetime.now(timezone.utc).isoformat()
    docs = T.records_to_docs(records, report_id, section_id)
    actions = []
    for d in docs:
        doc = {
            "report_id": d["report_id"],
            "section_id": d["section_id"],
            "section": section or d["section"],
            "company": company,
            "stock_code": stock_code,
            "year": year,
            "text": d["text"],
            "fields": d["fields"],
            "indexed_at": now,
        }
        actions.append({"index": {"_index": name, "_id": d["_id"]}})
        actions.append(doc)

    succeeded = failed = 0
    if actions:
        try:
            resp = es.bulk(operations=actions, refresh=True)
            for item in resp.get("items", []):
                if "error" in item.get("index", {}):
                    failed += 1
                else:
                    succeeded += 1
        except Exception as e:
            return {"error": f"bulk failed: {e}", "index": name}

    # refresh doc_count from the index
    try:
        count = es.count(index=name)["count"]
    except Exception:
        count = succeeded

    get_db().upsert_es_index(name, count, T.mapping_hash(mapping))
    return {
        "index": name,
        "succeeded": succeeded,
        "failed": failed,
        "doc_count": count,
    }


# ── Elasticsearch search tool ───────────────────────────────────


@app.tool
def search_reports(
    query: str,
    year: Optional[int] = None,
    company: Optional[str] = None,
    stock_code: Optional[str] = None,
    section: Optional[str] = None,
    from_: int = 0,
    size: int = 25,
) -> dict:
    """Full-text + filtered search over cnreport indices with highlights.

    Args:
        query: free-text query (matches the indexed text/fields).
        year: restrict to cnreport-{year}; None searches all cnreport-*.
        company/stock_code/section: optional term filters.
        from_/size: pagination; size capped at 50.
    """
    size = max(1, min(size, _MAX_SIZE))
    try:
        es = T.es_client()
    except Exception as e:
        return {"error": f"ES unavailable: {e}"}

    index = T.index_name_for(year) if year else "cnreport-*"
    filters = []
    if company:
        filters.append({"term": {"company": company}})
    if stock_code:
        filters.append({"term": {"stock_code": stock_code}})
    if section:
        filters.append({"term": {"section": section}})

    must = [{"match": {"text": query}}] if query else [{"match_all": {}}]
    body = {
        "from": from_,
        "size": size,
        "query": {"bool": {"must": must, "filter": filters}} if filters else {"bool": {"must": must}},
        "highlight": {"fields": {"text": {}}},
    }
    try:
        resp = es.search(index=index, body=body)
    except Exception as e:
        return {"error": f"search failed: {e}"}

    hits = []
    for h in resp["hits"]["hits"]:
        hits.append(
            {
                "id": h["_id"],
                "score": h.get("_score"),
                "source": h["_source"],
                "highlight": h.get("highlight", {}).get("text", []),
            }
        )
    return {
        "total": resp["hits"]["total"]["value"],
        "returned": len(hits),
        "hits": hits,
    }


@app.tool
def delete_index(year: int, confirm: bool = False) -> dict:
    """Drop the cnreport-{year} Elasticsearch index and its metadata row.

    Args:
        year: which index year to delete.
        confirm: must be True to actually delete.
    """
    if not confirm:
        return {"error": "pass confirm=true to delete"}
    try:
        es = T.es_client()
    except Exception as e:
        return {"error": f"ES unavailable: {e}"}
    name = T.index_name_for(year)
    try:
        es.indices.delete(index=name)
    except Exception as e:
        return {"error": f"delete failed: {e}"}
    get_db().remove_es_index(name)
    return {"deleted": name}


# ── company API tools (edgartools-style) ────────────────────────


@app.tool
def get_company(ticker_or_name: str) -> dict:
    """Resolve a CN-A-share company by 6-digit ticker or Chinese/English name fragment.

    Args:
        ticker_or_name: 6-digit ticker ("600519") or name fragment ("贵州茅台" / "MOUTAI").

    Returns: {stock_code, name, name_en, org_id, exchange, category} or {error}.
    """
    return T.get_company(ticker_or_name)


@app.tool
def list_filings(
    ticker_or_name: str,
    form: Optional[str] = None,
    category: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 20,
) -> dict:
    """List a CN-A-share company's CNINFO disclosures.

    Args:
        ticker_or_name: ticker or name (see get_company).
        form: optional Chinese form name (e.g. "年度报告", "半年度报告", "第一季度报告",
              "第三季度报告"). Free-text forms are filtered by title substring.
        category: optional CNINFO category — any catalog name (e.g. "招股说明书",
              "增发", "业绩预告") or raw `category_*` code. Use `list_report_types`
              to browse the catalog. Mutually exclusive with `form`; supplying both
              returns an error. Unknown categories return an error (no network call).
        year: optional fiscal-year filter (FY year, not publish year).
        limit: max rows to return (default 20).

    Each entry: {announcement_id, title, form, published, pdf_url, stock_code, company_name}.
    """
    result = T.list_filings(
        ticker_or_name, form=form, category=category, year=year, limit=limit
    )
    if isinstance(result, dict):  # error path
        return result
    return {"filings": result, "count": len(result)}


@app.tool
def get_filing(announcement_id: str, ticker_or_name: Optional[str] = None) -> dict:
    """Fetch one CNINFO announcement's metadata + PDF URL by id.

    Args:
        announcement_id: CNINFO announcementId.
        ticker_or_name: company hint to narrow the lookup (recommended).

    Returns: same shape as list_filings entries, or {error}.
    """
    return T.get_filing(announcement_id, ticker_or_name=ticker_or_name)


@app.tool
def get_financials(
    ticker_or_name: str,
    statement: Optional[str] = None,
    period: str = "annual",
) -> dict:
    """Return structured income/balance/cashflow statements for a CN-A-share company.

    Args:
        ticker_or_name: ticker or name (see get_company).
        statement: omit for all three; else one of
                   "income_statement" | "balance_sheet" | "cashflow".
        period: "annual" (default; keeps year-end rows) or "quarterly" (all periods).

    Each statement is serialized as {columns, data} (DataFrame.to_dict orient='split').
    """
    return T.get_financials(ticker_or_name, statement=statement, period=period)


@app.tool
def get_section(
    ticker_or_name: str,
    year: int,
    section: str,
    form: str = "年度报告",
) -> dict:
    """Resolve a company's filing PDF and extract one named section.

    Convenience wrapper: (ticker, year, section, form) → CNINFO lookup
    → PDF URL → existing outline-extraction pipeline.

    Args:
        ticker_or_name: ticker or name.
        year: fiscal year.
        section: exact title, regex, or 1-based ordinal — same selector
                 grammar as extract_section.
        form: form name; defaults to "年度报告".

    Returns: {stock_code, company_name, year, form, section, pdf_url,
              outline_entry, text, char_count} or {error}.
    """
    return T.get_section(ticker_or_name, year=year, section=section, form=form)


# ── report-type catalog + special-report tools ─────────────────


@app.tool
def list_report_types(group: Optional[str] = None) -> dict:
    """Browse the CNINFO disclosure category catalog.

    Args:
        group: optional group name to filter by (e.g. "定期报告", "融资", "业绩",
               "股权变动", "公司治理", "风险与特别处理"). Omit to list every group.

    Returns: each category as `{name, code, description}` plus a `count`.
    Useful before calling `list_filings(category=…)` or `get_special_report(…)`.
    """
    return T.list_report_types(group=group)


@app.tool
def get_special_report(
    ticker_or_name: str,
    category: str,
    year: Optional[int] = None,
    section: Optional[str] = None,
    limit: int = 5,
) -> dict:
    """Retrieve a special-type report for a CN-A-share company by CNINFO category.

    Args:
        ticker_or_name: ticker or name (see get_company).
        category: CNINFO category — a catalog name (e.g. "招股说明书", "收购报告书",
                  "业绩预告") or raw `category_*` code. Use `list_report_types` to browse.
        year: optional publish-year window (FY year for periodic reports).
        section: optional section selector (exact title, regex, or 1-based ordinal —
                 same grammar as `extract_section`). When omitted, the PDF is NOT
                 downloaded; only filing metadata + pdf_url are returned.
        limit: max filings to consider (default 5); the top (most recent) is used.

    Returns: filing metadata + pdf_url, plus section text/outline_entry/char_count
             when `section` is given; or an error field on unknown category / company / filing.
    """
    return T.get_special_report(
        ticker_or_name, category=category, year=year, section=section, limit=limit
    )


# ── three major financial statements (三大报表) ─────────────────


@app.tool
def get_financial_statements(
    ticker_or_name: str,
    year: int,
    form: str = "年度报告",
) -> dict:
    """Extract the three major financial statements (三大报表) as text.

    Resolves the company's filing PDF for ``(ticker, year, form)`` via the
    report cache (no re-download on repeat), parses the table of contents,
    and returns each statement's body text:

      - ``statements.income_statement`` (利润表)       — prefers 合并利润表
      - ``statements.balance_sheet`` (资产负债表)       — prefers 合并资产负债表
      - ``statements.cashflow`` (现金流量表)            — prefers 合并现金流量表

    Returns section **text only** — never PDF bytes. Statements not located
    in the TOC are listed in ``missing`` (with the full ``available`` title
    list so the caller can fall back to ``get_section`` with a custom selector).

    Args:
        ticker_or_name: ticker or name (see get_company).
        year: fiscal year.
        form: form name; defaults to "年度报告".

    Returns: {stock_code, company_name, year, form, pdf_url, cached,
              statements: {...}, missing: [...], available: [...]} or {error}.
    """
    return T.get_financial_statements(ticker_or_name, year, form=form)


# ── cache management tools ─────────────────────────────────────


@app.tool
def list_cache() -> dict:
    """List cached annual reports.

    Each entry carries the parsed provenance (``stock_code`` / ``year`` /
    ``form`` / ``announcement_id`` for convenience-tool fetches, or
    ``kind: "url"`` for raw ``extract_section``/``list_outline`` URL fetches),
    ``cached_at`` (file mtime, ISO-8601 UTC), and ``size`` (sum of its
    ``.pdf`` + ``.txt`` + ``.outline.json``).
    """
    import report_cache

    return report_cache.list_cache()


@app.tool
def clear_cache(
    stock_code: Optional[str] = None, year: Optional[int] = None
) -> dict:
    """Evict cached annual reports.

    Args:
        stock_code: when set, evict only entries for that stock.
        year: when set alongside ``stock_code``, evict only that stock+year.
              Both unset → evict everything.

    Returns: {removed, cache_dir}.
    """
    import report_cache

    return report_cache.clear_cache(stock_code=stock_code, year=year)


# ── indicator rules engine tools ─────────────────────────────────


@app.tool
def list_indicators(
    module: Optional[str] = None,
    query: Optional[str] = None,
    company: Optional[str] = None,
) -> dict:
    """Browse the banking-indicator rule set (data-driven by indicator_rules.json).

    Args:
        module: optional module filter — one of "balance_sheet", "income_statement",
                "cashflow", "financial_ratio". Unknown → error with available names.
        query: optional normalized substring match over indicator name + aliases.
        company: optional ticker or name — returns only the rules applicable to that
                 company (per `applies_to` + company profile) and includes the resolved
                 `{industry, sub_type}` profile. Useful to preview which indicators
                 will be processed before calling `extract_indicators`.

    Returns: grouped rules + `count` (+ `company_profile` when `company` is set), or {error}.
    """
    return T.list_indicators(module=module, query=query, company=company)


@app.tool
def get_indicator(
    indicator: str,
    ticker_or_name: str,
    year: int,
    period: str = "annual",
) -> dict:
    """Resolve one named financial indicator for a company + period.

    Routes per the rule's `source_type`: akshare line items, annual-report PDF
    section (LLM or registered Python extractor), or locally-computed ratio.

    Args:
        indicator: indicator name (exact, alias, or normalized substring) —
                   e.g. "资本充足率", "资产负债率", "营业收入".
        ticker_or_name: 6-digit ticker or name fragment (see get_company).
        year: fiscal year.
        period: "annual" (default) or "quarterly" (akshare only).

    Returns: {stock_code, company_name, year, indicator, value, unit, source_type,
              extractor, source, period, provenance, note} or {error}. `value` is
              `null` (not an error) when the indicator is applicable but not found.
    """
    return T.get_indicator(indicator, ticker_or_name, year=year, period=period)


@app.tool
def extract_indicators(
    ticker_or_name: str,
    year: int,
    indicators: Optional[list] = None,
    form: str = "年度报告",
    extractor_mode: str = "auto",
) -> dict:
    """Extract many indicators for one company/year in a single pass.

    Fetches the annual-report PDF once, groups report-rules by section (one LLM
    call per section), dispatches Python extractors individually, and computes
    derived ratios locally. Caches the bundle to disk so repeat calls are free.

    Args:
        ticker_or_name: ticker or name (see get_company).
        year: fiscal year.
        indicators: optional list of indicator names; omit to attempt every rule
                    applicable to the company. Unknown / non-applicable names go
                    to `missing`.
        form: form name; defaults to "年度报告".
        extractor_mode: "auto" (default — each rule's declared extractor),
                        "llm" (force LLM for report rules), or "python"
                        (skip report rules whose extractor is LLM — LLM-free run).

    Returns: {stock_code, company_name, year, form, pdf_url, cached, rules_hash,
              extractor_mode, indicators: {...}, missing: [...], unresolved: [...]}
              or {error}.
    """
    return T.extract_indicators(
        ticker_or_name, year, indicators=indicators, form=form, extractor_mode=extractor_mode,
    )


@app.tool
def extract_indicators_by_position(
    ticker_or_name: str,
    year: int,
    csv_path: str = "docs/indicators_position.csv",
    extractor: str = "auto",
    indicators: Optional[list] = None,
) -> dict:
    """Extract the indicators named in a position CSV for one company/year.

    Default CSV is `docs/indicators_position.csv` (override with `csv_path`).
    Reads the CSV's indicator column, routes report/akshare/computed indicators
    through the batch engine (one PDF fetch, batched LLM, python extractors,
    computed ratios, bundle cache), and lists realtime/external indicators
    (PE-TTM, PB, 市值, …) in `skipped` — they are not in the report PDF.

    Args:
        ticker_or_name: ticker or name (see get_company).
        year: fiscal year.
        csv_path: position CSV path (default docs/indicators_position.csv).
        extractor: "auto" (default — each rule's declared extractor), "llm"
                  (force LLM for report rules), or "python" (skip report rules
                  whose extractor is LLM — LLM-free run).
        indicators: optional subset — restricts extraction to the intersection
                    of this list and the CSV's indicator column.

    Returns: {stock_code, company_name, year, form, pdf_url, cached, indicators,
              missing, unresolved, skipped, csv_path} or {error}.
    """
    return T.extract_indicators_by_position(
        ticker_or_name, year, csv_path=csv_path, extractor=extractor, indicators=indicators,
    )


# ── HK stock tools ────────────────────────────────────────────────


@app.tool
def get_hk_company(ticker_or_name: str) -> dict:
    """Resolve a HK stock company by 5-digit ticker or name fragment.

    Args:
        ticker_or_name: ticker ("00700") or name fragment ("腾讯").

    Returns: {stock_code, name, name_en, industry, employees, description, website}
             or {error}.
    """
    return T.get_hk_company(ticker_or_name)


@app.tool
def list_hk_filings(
    ticker_or_name: str,
    form: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 20,
) -> dict:
    """List a HK stock company's filings/announcements.

    Args:
        ticker_or_name: HK stock ticker or name.
        form: optional form type filter (e.g. "年报").
        year: optional year filter.
        limit: max results (default 20).

    Returns: {filings, count} or {error}.
    """
    result = T.list_hk_filings(
        ticker_or_name, form=form, year=year, limit=limit,
    )
    if isinstance(result, dict) and "error" in result:
        return result
    return {"filings": result, "count": len(result) if isinstance(result, list) else 0}


@app.tool
def get_hk_financials(ticker_or_name: str) -> dict:
    """Return structured financial statements for a HK stock company.

    Args:
        ticker_or_name: HK stock ticker or name.

    Returns: {stock_code, company_name, income_statement, balance_sheet, cashflow}
             or {error}.
    """
    return T.get_hk_financials(ticker_or_name)


@app.tool
def get_hk_section(
    ticker_or_name: str,
    year: int,
    section: str,
) -> dict:
    """Extract a named section from a HK stock annual report PDF.

    Args:
        ticker_or_name: HK stock ticker or name.
        year: fiscal year.
        section: section title selector.

    Returns: {stock_code, company_name, year, section, pdf_url,
              outline_entry, text, char_count} or {error}.
    """
    return T.get_hk_section(ticker_or_name, year, section)


@app.tool
def audit_rule_gaps(
    out_dir: str = "out",
    output_path: str = "docs/rule_gap_audit.json",
    max_files: int = 0,
) -> dict:
    """Audit rule gaps from existing out/ bundles and write a stable JSON report.

    Args:
        out_dir: directory containing extracted bundles (default "out").
        output_path: path to write the audit report JSON (default docs/rule_gap_audit.json).
        max_files: optional cap on number of bundles scanned (0 = no cap).

    Returns: {output_path, report} or {error}.
    """
    return T.audit_rule_gaps(out_dir=out_dir, output_path=output_path, max_files=max_files)


@app.tool
def open_industry_rules_dashboard(port: int = 8888) -> dict:
    """Start the industry rules web dashboard with filtering and search.

    Opens a web UI at http://localhost:<port> showing all 21,698 LLM rules
    across 31 申万 L1 industries. Filter by industry, module, keyword; sort
    by any column; paginated view.

    Args:
        port: TCP port to listen on (default 8888).
    """
    from scripts.industry_rules_dashboard import start_dashboard
    start_dashboard(port)


if __name__ == "__main__":
    app.run(transport="stdio", show_banner=False)
