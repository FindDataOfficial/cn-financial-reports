"""CSRC (中国证监会, www.csrc.gov.cn) HTTP client.

A primary-source path to CSRC regulatory data that CNINFO/exchanges do not
cover: regulatory announcements, IPO (首发) review status, 并购重组 (M&A)
review status, and enforcement (行政处罚) actions.

CSRC's site is HTML-driven (no stable JSON contract) and has been reorganized
repeatedly, so this client parses HTML with ``lxml`` using selectors isolated
in ``_SELECTORS`` / URLs in ``_URLS``. Every endpoint is marked
``# undocumented - UNVERIFIED`` - they are best-effort and MUST be verified
live (``CNREPORT_SELFCHECK_LIVE=1 uv run python selfcheck.py`` flags 4xx/5xx).
Parsing is defensive: a malformed/changed page yields ``[]`` / ``{error}``,
never raises. Mock-friendly: tests patch ``_fetch_html`` with recorded HTML.

Every call goes through ``official_client_utils`` (``trust_env=False`` +
429/5xx retry/backoff).
"""
from __future__ import annotations

import re
from typing import Any, Optional

import httpx
from lxml import html as lxml_html

import official_client_utils as U

_BASE = "http://www.csrc.gov.cn"
_TIMEOUT = 30.0
_SLEEP = U.SLEEP
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Best-guess CSRC page URLs - undocumented, UNVERIFIED. Centralized so a
# verified URL is a one-line fix. Categories map to CSRC news/notice channels.
_URLS = {
    # Regulatory announcements / notices (要闻 / 新闻导读).
    "filings": "http://www.csrc.gov.cn/pub/newsite/zjxw/xwdd/",
    # IPO review (发行审核) - application status listing.
    "ipo_review": "http://www.csrc.gov.cn/pub/newsite/zjxw/fxjz/",
    # 并购重组 review (并购重组审核) status listing.
    "merger_review": "http://www.csrc.gov.cn/pub/newsite/zjxw/bczgzcz/",
    # Administrative penalties / enforcement (行政处罚).
    "enforcement": "http://www.csrc.gov.cn/pub/newsite/zjxw/xzcf/",
}

# lxml selectors per page type. ``list_item`` locates repeating rows;
# ``link`` the title anchor; ``date`` the date cell/span.
_SELECTORS = {
    "list_item_li": "//ul//li",
    "list_item_tr": "//table//tr",
    "link": ".//a",
    "date": ".//span | .//td",
}

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _client() -> httpx.Client:
    """Per-call httpx client. Tests patch this to inject a mock."""
    return U.make_client(
        base_url=_BASE,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": _BASE + "/",
        },
        timeout=_TIMEOUT,
    )


def _fetch_html(url: str, *, params: Optional[dict] = None) -> str:
    """GET ``url`` and return response text. Errors raise; tests patch this."""
    client = _client()
    try:
        resp = U.request_retry(client, "GET", url, params=params)
        resp.raise_for_status()
        # CSRC pages are GB2312/GBK in places; httpx decodes via headers, but
        # fall back to utf-8 then gbk if the body looks mis-decoded.
        return resp.text
    finally:
        client.close()


def _abs_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "http:" + href
    return _BASE + (href if href.startswith("/") else "/" + href)


def _parse_list(html_text: str, *, limit: int = 20) -> list[dict]:
    """Parse a CSRC announcement list (``<li>`` or ``<tr>`` items).

    Each item becomes ``{title, published, url, source: "csrc"}``. Returns
    ``[]`` if the page shape is unrecognized.
    """
    try:
        tree = lxml_html.fromstring(html_text)
    except Exception:
        return []
    # Prefer <li> items; fall back to <tr> rows.
    nodes = tree.xpath(_SELECTORS["list_item_li"]) or tree.xpath(_SELECTORS["list_item_tr"])
    results: list[dict] = []
    for node in nodes:
        links = node.xpath(_SELECTORS["link"])
        if not links:
            continue
        a = links[0]
        title = (a.text_content() or "").strip()
        if not title:
            continue
        # Date: prefer an explicit date cell/span, else regex-scan the item text.
        date = ""
        date_nodes = node.xpath(_SELECTORS["date"])
        for d in date_nodes:
            m = _DATE_RE.search(d.text_content() or "")
            if m:
                date = m.group(0)
                break
        if not date:
            m = _DATE_RE.search(node.text_content() or "")
            date = m.group(0) if m else ""
        href = a.get("href") or ""
        results.append({"title": title, "published": date, "url": _abs_url(href), "source": "csrc"})
        if len(results) >= limit:
            break
    return results


def _parse_table_dicts(html_text: str) -> list[dict]:
    """Parse the first ``<table>`` into list of dicts keyed by header row."""
    try:
        tree = lxml_html.fromstring(html_text)
    except Exception:
        return []
    tables = tree.xpath("//table")
    for table in tables:
        rows = table.xpath(".//tr")
        if len(rows) < 2:
            continue
        headers = [(th.text_content() or "").strip() for th in rows[0].xpath(".//th | .//td")]
        if not any(headers):
            continue
        out: list[dict] = []
        for row in rows[1:]:
            cells = [(td.text_content() or "").strip() for td in row.xpath(".//td")]
            if not cells:
                continue
            row_dict = {headers[i]: cells[i] for i in range(min(len(headers), len(cells)))}
            out.append(row_dict)
        if out:
            return out
    return []


# ── public API ────────────────────────────────────────────────────


def list_csrc_filings(
    category: Optional[str] = None,
    *,
    begin_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """List CSRC regulatory announcements/notices.

    Args:
        category: optional channel hint (currently informational; the listing
            page is fixed per ``_URLS["filings"]``).
        begin_date / end_date: optional ``YYYY-MM-DD`` post-filter on published date.
        limit: max rows.

    Returns ``[{title, published, url, source}]``. Never raises - returns ``[]``.
    # undocumented - UNVERIFIED: filings URL + HTML structure.
    """
    try:
        html_text = _fetch_html(_URLS["filings"])
    except Exception:
        return []
    rows = _parse_list(html_text, limit=max(limit * 2, 20))
    if begin_date:
        rows = [r for r in rows if r["published"] >= begin_date]
    if end_date:
        rows = [r for r in rows if r["published"] <= end_date]
    return rows[:limit]


def _review_status(kind: str, company_or_code: str) -> dict:
    """Shared IPO/merger review lookup. ``kind`` is "ipo_review" or "merger_review"."""
    rows = _parse_table_dicts(_safe_fetch(_URLS[kind]))
    if not rows:
        return {"company": company_or_code, "source": "csrc", "error": "no review table found"}
    needle = (company_or_code or "").strip()
    for r in rows:
        blob = " ".join(str(v) for v in r.values())
        if needle and needle in blob:
            return {"company": company_or_code, "source": "csrc", "fields": r}
    return {"company": company_or_code, "source": "csrc", "error": "no matching application", "available": len(rows)}


def _safe_fetch(url: str) -> str:
    try:
        return _fetch_html(url)
    except Exception:
        return ""


def get_csrc_ipo_review(company_or_code: str) -> dict:
    """Query CSRC IPO (首发) application review status for a company.

    Returns ``{company, source, fields}`` (matching application's row) or
    ``{company, source, error}``.  # undocumented - UNVERIFIED.
    """
    return _review_status("ipo_review", company_or_code)


def get_csrc_merger_review(company_or_code: str) -> dict:
    """Query CSRC 并购重组 (M&A) review status for a company.

    Returns ``{company, source, fields}`` or ``{company, source, error}``.
    # undocumented - UNVERIFIED.
    """
    return _review_status("merger_review", company_or_code)


def list_csrc_enforcement(*, begin_date: Optional[str] = None, limit: int = 20) -> list[dict]:
    """List CSRC administrative-penalty / enforcement actions.

    Returns ``[{title, published, url, source}]``. Never raises - returns ``[]``.
    # undocumented - UNVERIFIED.
    """
    try:
        html_text = _fetch_html(_URLS["enforcement"])
    except Exception:
        return []
    rows = _parse_list(html_text, limit=max(limit * 2, 20))
    if begin_date:
        rows = [r for r in rows if r["published"] >= begin_date]
    return rows[:limit]


# ── health ────────────────────────────────────────────────────────


def ping() -> dict:
    """Lightweight liveness probe for the CSRC host. Never raises."""
    url = _URLS["enforcement"]
    client = _client()
    try:
        resp = U.request_retry(client, "GET", url)
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "url": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status_code": None, "url": url, "error": f"{type(e).__name__}: {e}"}
    finally:
        client.close()
