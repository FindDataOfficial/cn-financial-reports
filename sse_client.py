"""SSE (上海证券交易所, www.sse.com.cn) HTTP client.

A direct, primary-source path to SSE-listed company disclosures that complements
the CNINFO aggregator already wired in ``cninfo_client``. Two undocumented,
keyless JSON endpoints power the SSE disclosure SPA:

  query.sse.com.cn/security/stock/queryCompanyBulletin.do  - list bulletins
  static.sse.com.cn/<URL>                                  - PDF download URL
  sns.sseinfo.com/ajax/queryApi.do                         - 上证e互动 Q&A

These endpoints are undocumented and shift over time; every call goes through
``official_client_utils`` (``trust_env=False`` + 429/5xx retry/backoff) and is
marked ``# undocumented - verify live``. ``selfcheck.py`` (with
``CNREPORT_SELFCHECK_LIVE=1``) flags 4xx/5xx per source without failing the
suite. Mock-friendly: tests patch ``_post_form`` / ``_client``, not httpx.

Company resolution is code-based and local (no network): SSE codes are
600/601/603/605/688/900. Name-fragment resolution is not supported by this
client (no reliable SSE search endpoint) - resolve the name via
``get_company`` (CNINFO) first, then pass the 6-digit code here.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

import official_client_utils as U

_BASE = "http://query.sse.com.cn"
_STATIC = "http://static.sse.com.cn/"
_INTERACTION = "http://sns.sseinfo.com"
_TIMEOUT = 30.0
_SLEEP = U.SLEEP
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# SSE 6-digit code prefixes: main board 600/601/603/605, STAR 688, B-shares 900.
_SSE_PREFIXES = ("600", "601", "603", "605", "688", "900")


def _client() -> httpx.Client:
    """Per-call httpx client. Tests patch this to inject a mock."""
    return U.make_client(
        base_url=_BASE,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "http://www.sse.com.cn/",
            "Origin": "http://www.sse.com.cn",
        },
        timeout=_TIMEOUT,
    )


def _unwrap_jsonp(text: str) -> Any:
    """Parse a JSON or JSONP-wrapped response body.

    SSE endpoints wrap responses as ``jsonpCallback({...})`` when a
    ``jsonCallBack`` parameter is sent. We send an empty callback and also
    defensively strip any ``name(`` ... ``)`` wrapper here.
    """
    text = text.strip()
    if text and text[0] == "{":
        return json.loads(text)
    m = re.match(r"^[\s$._a-zA-Z0-9]+\((.*)\)\s*;?\s*$", text, re.S)
    if m:
        return json.loads(m.group(1))
    return json.loads(text)  # let json raise on truly malformed input


def _post_form(path: str, data: dict[str, Any], *, base: str = _BASE) -> Any:
    """POST form-encoded data to ``base+path`` and return parsed JSON.

    Errors raise (callers wrap with try/except or ``_tool_safe``). Tests patch
    this to inject canned responses.
    """
    client = _client()
    try:
        resp = U.request_retry(
            client, "POST", path, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        resp.raise_for_status()
        return _unwrap_jsonp(resp.text)
    finally:
        client.close()


def _interaction_post(path: str, data: dict[str, Any]) -> Any:
    """POST to the 上证e互动 host (sns.sseinfo.com) and return parsed JSON.

    Separate from ``_post_form`` because the interaction host needs its own
    Referer/base. Tests patch this to inject canned responses.
    """
    client = U.make_client(
        base_url=_INTERACTION,
        headers={"User-Agent": _UA, "Referer": "http://sns.sseinfo.com/"},
        timeout=_TIMEOUT,
    )
    try:
        resp = U.request_retry(
            client, "POST", path, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                     "X-Requested-With": "XMLHttpRequest"},
        )
        resp.raise_for_status()
        return _unwrap_jsonp(resp.text)
    finally:
        client.close()


# ── company resolution (code-based, local) ────────────────────────


def _is_sse_code(code: str) -> bool:
    return bool(code) and code.isdigit() and len(code) == 6 and code[:3] in _SSE_PREFIXES


def lookup_sse_company(ticker_or_name: str) -> Optional[dict]:
    """Resolve an SSE-listed company by 6-digit ticker.

    Returns ``{stock_code, exchange, source, name}`` for a valid SSE code, or
    ``None`` for anything else (name fragments are not supported here - resolve
    via CNINFO's ``get_company`` first). Pure-local, no network call.
    """
    code = (ticker_or_name or "").strip()
    if not _is_sse_code(code):
        return None
    return {"stock_code": code, "exchange": "sse", "source": "sse", "name": ""}


# ── disclosure listing ────────────────────────────────────────────


def _window_for_year(year: Optional[int]) -> tuple[str, str]:
    """Return (beginDate, endDate) for a fiscal-year filter.

    SSE annual reports for FY{year} publish in {year+1}; widen the window so
    periodic reports in their natural publish window are caught too.
    """
    if year is None:
        return "", ""
    return f"{year}-01-01", f"{year + 1}-12-31"


def _form_from_title(title: str) -> str:
    if not title:
        return ""
    for form in ("半年度报告", "第一季度报告", "第三季度报告", "年度报告", "招股说明书"):
        if form in title:
            return form
    return ""


def _map_bulletin(row: dict, stock_code: str) -> dict:
    url = row.get("URL") or ""
    if url and not url.startswith("http"):
        url = _STATIC + url.lstrip("/")
    published = ""
    raw_date = row.get("ADVISE_DATE") or ""
    if raw_date:
        try:
            published = str(raw_date)[:10]  # SSE returns YYYY-MM-DD or YYYYMMDD
            if published.isdigit() and len(published) == 8:
                published = f"{published[:4]}-{published[4:6]}-{published[6:]}"
        except Exception:
            published = str(raw_date)
    return {
        "announcement_id": str(row.get("BULLETIN_ID") or row.get("id") or ""),
        "title": row.get("BULLETIN_TITLE") or "",
        "form": _form_from_title(row.get("BULLETIN_TITLE") or ""),
        "published": published,
        "pdf_url": url,
        "stock_code": stock_code,
        "source": "sse",
    }


def list_sse_filings(
    stock_code: str,
    *,
    title: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    """List SSE disclosures (bulletins) for a company.

    Args:
        stock_code: 6-digit SSE ticker.
        title: optional title-substring filter (e.g. "年度报告").
        year: optional fiscal-year filter (maps to a publish-date window).
        limit: max rows to return (page size is over-fetched then truncated).

    Returns a list of ``{announcement_id, title, form, published, pdf_url,
    stock_code, source}``. Never raises on a missing company / empty result -
    returns ``[]``.  # undocumented - verify live: queryCompanyBulletin.do
    """
    code = (stock_code or "").strip()
    if not _is_sse_code(code):
        return []
    page_size = max(1, min(int(limit) * 2 + 10, 50))
    begin, end = _window_for_year(year)
    data: dict[str, Any] = {
        "jsonCallBack": "",
        "isPagination": "true",
        "pageNo": "1",
        "pageSize": str(page_size),
        "beginDate": begin,
        "endDate": end,
        "securityCode": code,
        "title": title or "",
        "bulletinType": "",
        "BulletinType": "",
        "source": "",
        "_": "",
    }
    try:
        payload = _post_form("/security/stock/queryCompanyBulletin.do", data)
    except Exception:
        return []
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("result") or []
    if not isinstance(rows, list):
        rows = []
    results = [_map_bulletin(r, code) for r in rows if isinstance(r, dict)]
    # Post-hoc year filter: periodic-report titles embed the fiscal year.
    if year is not None:
        results = [r for r in results if str(year) in (r.get("title") or "")]
    return results[:limit]


def get_sse_annual_report_filing(stock_code: str, year: int) -> Optional[dict]:
    """Pick the FY{year} annual-report filing from the SSE disclosure list."""
    rows = list_sse_filings(stock_code, title="年度报告", year=year, limit=10)
    for r in rows:
        if r.get("pdf_url") and "年度报告" in (r.get("title") or ""):
            return r
    for r in rows:
        if r.get("pdf_url"):
            return r
    return None if not rows else rows[0]


# ── 上证e互动 (investor Q&A) ──────────────────────────────────────


def get_sse_interaction(stock_code: str, *, limit: int = 20) -> dict:
    """Fetch 上证e互动 investor Q&A for an SSE-listed company.

    Returns ``{stock_code, source, questions: [{question, answer, questioner,
    asked, answered}]}`` or ``{stock_code, source, error}`` on failure.
    # undocumented - verify live: sns.sseinfo.com/ajax/queryApi.do
    """
    code = (stock_code or "").strip()
    if not _is_sse_code(code):
        return {"stock_code": code, "source": "sseinfo", "error": "not an SSE code"}
    page_size = max(1, min(int(limit), 50))
    data = {"stockCode": code, "pageNo": "1", "pageSize": str(page_size), "type": "0"}
    try:
        payload = _interaction_post("/ajax/queryApi.do", data)
    except Exception as e:  # noqa: BLE001 - miss-tolerant
        return {"stock_code": code, "source": "sseinfo", "error": f"{type(e).__name__}: {e}"}

    questions = []
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("result") or payload.get("data") or payload.get("questions") or []
    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            questions.append({
                "question": r.get("question") or r.get("content") or r.get("title") or "",
                "answer": r.get("answer") or r.get("reply") or r.get("replyContent") or "",
                "questioner": r.get("questioner") or r.get("asked_by") or "",
                "asked": r.get("asked") or r.get("questionDate") or "",
                "answered": r.get("answered") or r.get("replyDate") or "",
            })
    return {"stock_code": code, "source": "sseinfo", "questions": questions[:limit]}


# ── health ────────────────────────────────────────────────────────


def ping() -> dict:
    """Lightweight liveness probe for the SSE disclosure host. Never raises."""
    url = _BASE + "/security/stock/queryCompanyBulletin.do"
    client = _client()
    try:
        resp = U.request_retry(
            client, "POST", "/security/stock/queryCompanyBulletin.do",
            data={"jsonCallBack": "", "isPagination": "true", "pageNo": "1",
                  "pageSize": "1", "securityCode": "600000", "beginDate": "",
                  "endDate": "", "title": "", "bulletinType": "", "_": ""},
        )
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "url": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status_code": None, "url": url, "error": f"{type(e).__name__}: {e}"}
    finally:
        client.close()
