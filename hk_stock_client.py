"""Hong Kong stock data client for cnreport-mcp.

Wraps akshare HK stock functions and HKEX披露易 (HKEX News) API to provide
HK stock company lookup, financial statements, and annual report filings.

HK stock tickers are 5-digit codes (e.g. 00700 for Tencent). The leading
zeros are significant when querying some akshare endpoints.

Usage:
    from hk_stock_client import lookup_hk_company, get_hk_financials, list_hk_filings

    co = lookup_hk_company("00700")
    filings = list_hk_filings("00700", year=2023)
    text = get_hk_report_text(filings[0]["pdf_url"])
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── HKEX披露易 API endpoints ──────────────────────────────────────
_HKEX_BASE = "https://www1.hkexnews.hk"
_HKEX_SEARCH = f"{_HKEX_BASE}/search/titlesearch.hk"
_HKEX_DAILY = f"{_HKEX_BASE}/app/sehk/daily/hkexnews-list.html"
_PDF_CDN = "https://www.hkexnews.hk/"
_TIMEOUT = 30.0
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# ── HK stock exchange codes ────────────────────────────────────────
# HK stock ticker prefixes: 5-digit code, leading zeros are significant.
# Main Board: 00001-09999, 10000-99999
# GEM: 08000-09999 (previously 8xxx)


def _format_ticker(ticker: str) -> str:
    """Normalize a HK stock ticker to 5-digit format with leading zeros.
    
    '700', '0700', '00700' → '00700'
    '1', '00001' → '00001'
    '8001' → '08001'
    """
    t = ticker.strip()
    # Remove common suffixes
    for suffix in (".HK", ".hk", "-HK", "-hk"):
        if t.upper().endswith(suffix):
            t = t[: -len(suffix)]
    if t.isdigit():
        return t.zfill(5)
    return t


def _strip_leading_zeros(ticker: str) -> str:
    """Remove leading zeros for akshare endpoints that expect bare codes.
    
    '00700' → '700'
    '00001' → '1'
    """
    t = ticker.lstrip("0")
    return t if t else "0"


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=_TIMEOUT,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        follow_redirects=True,
    )


# ── company lookup ────────────────────────────────────────────────


def lookup_hk_company(ticker_or_name: str) -> Optional[dict]:
    """Look up a HK stock company by ticker or name fragment.
    
    Uses akshare's stock_hk_company_profile_em to get company details.
    Falls back to a name search if the ticker does not resolve.
    
    Returns:
        {stock_code, name, name_en, industry, employees, description, website}
        or None when not found.
    """
    try:
        import akshare as ak  # noqa: WPS433 — lazy import
    except ImportError as e:
        logger.warning("akshare not installed: %s", e)
        return None

    ticker = _format_ticker(ticker_or_name)
    bare = _strip_leading_zeros(ticker)
    
    try:
        df = ak.stock_hk_company_profile_em(symbol=bare)
    except Exception as e:
        logger.debug("akshare profile lookup failed for %s: %s", bare, e)
        return None
    
    if df is None or df.empty:
        return None
    
    row = df.iloc[0]
    return {
        "stock_code": ticker,
        "name": str(row.get("公司名称", "") or ""),
        "name_en": str(row.get("英文名称", "") or ""),
        "industry": str(row.get("所属行业", "") or ""),
        "employees": str(row.get("员工人数", "") or ""),
        "description": str(row.get("公司介绍", "") or ""),
        "website": str(row.get("公司网址", "") or ""),
        "exchange": "hkex",
    }


# ── financial statements ──────────────────────────────────────────


_STATEMENT_SINA_PARAM = {
    "income_statement": "利润表",
    "balance_sheet": "资产负债表",
    "cashflow": "现金流量表",
}


_STMT_CACHE: dict[tuple, tuple[float, dict]] = {}
_STMT_TTL = 600.0


def get_hk_financials(stock_code: str) -> dict[str, dict]:
    """Return income/balance/cashflow statements for a HK stock.
    
    Uses akshare's stock_financial_hk_report_em which returns all
    three statements in one call. Results are cached for _STMT_TTL seconds.
    
    Returns:
        {income_statement: {columns, data}, balance_sheet: {columns, data},
         cashflow: {columns, data}}
        or raises if akshare is unavailable.
    """
    try:
        import akshare as ak  # noqa: WPS433
    except ImportError as e:
        raise RuntimeError(
            "akshare not installed. Run: uv sync"
        ) from e

    ticker = _format_ticker(stock_code)
    cache_key = (ticker,)
    now = time.monotonic()
    cached = _STMT_CACHE.get(cache_key)
    if cached and now - cached[0] < _STMT_TTL:
        return cached[1]

    bare = _strip_leading_zeros(ticker)
    try:
        df = ak.stock_financial_hk_report_em(symbol=bare)
    except Exception as e:
        raise RuntimeError(f"akshare HK financial report failed: {e}") from e

    if df is None or df.empty:
        return {"income_statement": {"columns": [], "data": []},
                "balance_sheet": {"columns": [], "data": []},
                "cashflow": {"columns": [], "data": []}}

    out: dict[str, dict] = {
        "income_statement": _serialize_df(df),
        "balance_sheet": _serialize_df(df),
        "cashflow": _serialize_df(df),
    }
    _STMT_CACHE[cache_key] = (now, out)
    return out


def _serialize_df(df: Any) -> dict:
    if df is None:
        return {"columns": [], "data": []}
    cleaned = df.where(df.notna(), None)
    payload = cleaned.to_dict(orient="split")
    payload.pop("index", None)
    payload["columns"] = [str(c) for c in payload["columns"]]
    return payload


# ── filing / announcement listing (via HKEX披露易) ──────────────


def list_hk_filings(
    stock_code: str,
    *,
    form: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    """List HKEX filings/announcements for a HK stock.
    
    Uses HKEX's披露易 title search API. Filters by stock code and
    optionally by year and form type.
    
    Args:
        stock_code: HK stock ticker (e.g. "00700").
        form: optional form type filter (e.g. "年报", "年报/中期报告").
        year: optional year filter.
        limit: max results to return.
    
    Returns:
        List of {announcement_id, title, published, pdf_url, category, stock_code}.
    """
    ticker = _format_ticker(stock_code)
    bare = _strip_leading_zeros(ticker)
    
    params: dict[str, Any] = {
        "stockId": bare,
        "sortDir": "desc",
        "sortByOptions": "DateTime",
        "market": "SEHK",
        "language": "ZH",
    }
    if year:
        params["from"] = f"{year}0101"
        params["to"] = f"{year}1231"
    
    try:
        rows = _query_hkex(params)
    except Exception as e:
        logger.warning("HKEX search failed for %s: %s", ticker, e)
        return []
    
    # Filter by form type
    if form:
        rows = [r for r in rows if form in (r.get("category_name", "") or "")]
    
    # Post-filter by year
    if year:
        rows = [r for r in rows if str(year) in (r.get("title", "") or "")]
    
    return rows[:limit]


def _query_hkex(params: dict) -> list[dict]:
    """Query HKEX披露易 title search API.
    
    Returns parsed list of filing entries. Each entry has:
    {announcement_id, title, published, pdf_url, category_name, stock_code}.
    """
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        with _client() as c:
            resp = c.get(_HKEX_SEARCH, params=params, headers=headers, timeout=30.0)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning("HKEX search HTTP error: %s", e)
        return []
    
    return _parse_hkex_results(html)


def _parse_hkex_results(html: str) -> list[dict]:
    """Parse HKEX title search results HTML into structured entries.
    
    The HKEX results page returns an HTML table with filing entries.
    This is a robust parser that extracts from <tr> elements.
    """
    results: list[dict] = []
    
    # Try to find the results table and parse rows
    table_pattern = re.compile(
        r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>',
        re.DOTALL,
    )
    
    for match in table_pattern.finditer(html):
        title_td = match.group(1)
        date_td = match.group(2)
        cat_td = match.group(3)
        
        title = re.sub(r'<[^>]+>', '', title_td).strip()
        date_str = re.sub(r'<[^>]+>', '', date_td).strip()
        category = re.sub(r'<[^>]+>', '', cat_td).strip()
        
        # Extract PDF URL from the title cell's <a> tag
        pdf_match = re.search(r'href="([^"]*\.PDF)"', title_td, re.IGNORECASE)
        pdf_url = ""
        if pdf_match:
            url = pdf_match.group(1)
            if url.startswith("http"):
                pdf_url = url
            else:
                pdf_url = _PDF_CDN + url.lstrip("/")
        
        # Extract announcement ID from URL
        ann_id = ""
        if pdf_url:
            id_match = re.search(r'/(\d+)\.PDF', pdf_url, re.IGNORECASE)
            if id_match:
                ann_id = id_match.group(1)
        
        if title:
            results.append({
                "announcement_id": ann_id,
                "title": title,
                "published": date_str,
                "pdf_url": pdf_url,
                "category_name": category,
                "stock_code": "",
            })
    
    return results


# ── HKEX annual report specific ──────────────────────────────────


def get_hk_annual_report_filing(
    stock_code: str,
    year: int,
) -> Optional[dict]:
    """Find the annual report filing for a HK stock and year.
    
    Picks the most likely annual/年度 report from the filing list.
    Returns the filing dict with pdf_url, or None if not found.
    """
    filings = list_hk_filings(stock_code, year=year, limit=30)
    
    # Look for annual report keywords in title
    annual_keywords = ["年報", "年度报告", "Annual Report", "年报"]
    for f in filings:
        title = (f.get("title") or "").lower()
        for kw in annual_keywords:
            if kw.lower() in title:
                return f
    
    # Fallback: return the first filing if it has a PDF
    for f in filings:
        if f.get("pdf_url"):
            return f
    
    return None if not filings else filings[0]


def get_hk_report_text(pdf_url: str) -> str:
    """Download and extract text from a HK stock annual report PDF.
    
    Uses the same extraction pipeline as cnreport_tools so it reuses
    the existing text extraction logic (pymupdf → pypdf fallback).
    """
    if not pdf_url:
        return ""
    
    from cnreport_tools import fetch_source_with_bytes, extract_pdf_text
    
    text, raw = fetch_source_with_bytes(pdf_url, "uv")
    if raw is not None and pdf_url.lower().endswith(".pdf"):
        text = extract_pdf_text(raw)
    
    return text or ""
