"""SZSE (深圳证券交易所, www.szse.cn) HTTP client.

A direct, primary-source path to SZSE-listed company disclosures that
complements the CNINFO aggregator. Two undocumented, keyless endpoints power
the SZSE disclosure SPA:

  www.szse.cn/api/disc/announcement/annList   - list announcements (JSON POST)
  irm.cninfo.com.cn/ircs/...                  - 互动易 investor Q&A
                                                 (SZSE's Q&A, hosted by CNINFO)

These endpoints are undocumented and shift over time; every call goes through
``official_client_utils`` (``trust_env=False`` + 429/5xx retry/backoff) and is
marked ``# undocumented - verify live``. Mock-friendly: tests patch
``_post_json`` / ``_interaction_post``, not httpx.

Company resolution is code-based and local (no network): SZSE codes are
000/001/002/003/300/301. Name-fragment resolution is not supported here -
resolve the name via ``get_company`` (CNINFO) first, then pass the 6-digit code.

Open question (design.md): SZSE 互动易 is hosted on ``irm.cninfo.com.cn``; this
client exposes it under ``get_szse_interaction`` rather than as a cninfo
extension, so SZSE investor Q&A has a single entry point.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

import official_client_utils as U

_BASE = "http://www.szse.cn"
_INTERACTION = "http://irm.cninfo.com.cn"
_TIMEOUT = 30.0
_SLEEP = U.SLEEP
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# SZSE 6-digit code prefixes: main board 000/001, SME 002/003, ChiNext 300/301.
_SZSE_PREFIXES = ("000", "001", "002", "003", "300", "301")


def _client() -> httpx.Client:
    """Per-call httpx client. Tests patch this to inject a mock."""
    return U.make_client(
        base_url=_BASE,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "http://www.szse.cn/disclosure/listed/notice/index.html",
            "Origin": "http://www.szse.cn",
        },
        timeout=_TIMEOUT,
    )


def _post_json(path: str, body: dict[str, Any]) -> Any:
    """POST a JSON body to ``_BASE+path`` and return parsed JSON. Tests patch this."""
    client = _client()
    try:
        resp = U.request_retry(
            client, "POST", path, json=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()
    finally:
        client.close()


def _interaction_post(path: str, data: dict[str, Any]) -> Any:
    """POST to the 互动易 host (irm.cninfo.com.cn) and return parsed JSON."""
    client = U.make_client(
        base_url=_INTERACTION,
        headers={"User-Agent": _UA, "Referer": "http://irm.cninfo.com.cn/ircs/"},
        timeout=_TIMEOUT,
    )
    try:
        resp = U.request_retry(
            client, "POST", path, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                     "X-Requested-With": "XMLHttpRequest"},
        )
        resp.raise_for_status()
        return resp.json()
    finally:
        client.close()


# ── company resolution (code-based, local) ────────────────────────


def _is_szse_code(code: str) -> bool:
    return bool(code) and code.isdigit() and len(code) == 6 and code[:3] in _SZSE_PREFIXES


def lookup_szse_company(ticker_or_name: str) -> Optional[dict]:
    """Resolve a SZSE-listed company by 6-digit ticker.

    Returns ``{stock_code, exchange, source, name}`` for a valid SZSE code, or
    ``None`` otherwise. Pure-local, no network call.
    """
    code = (ticker_or_name or "").strip()
    if not _is_szse_code(code):
        return None
    return {"stock_code": code, "exchange": "szse", "source": "szse", "name": ""}


# ── disclosure listing ────────────────────────────────────────────


def _form_from_title(title: str) -> str:
    if not title:
        return ""
    for form in ("半年度报告", "第一季度报告", "第三季度报告", "年度报告", "招股说明书"):
        if form in title:
            return form
    return ""


def _map_announcement(row: dict, stock_code: str) -> dict:
    url = row.get("attachPath") or row.get("adjunctUrl") or row.get("url") or ""
    if url and not url.startswith("http"):
        url = _BASE + "/" + url.lstrip("/")
    return {
        "announcement_id": str(row.get("id") or row.get("announcementId") or ""),
        "title": row.get("title") or row.get("announcementTitle") or "",
        "form": _form_from_title(row.get("title") or ""),
        "published": (row.get("seDate") or row.get("noticeDate") or "")[:10],
        "pdf_url": url,
        "stock_code": stock_code,
        "source": "szse",
    }


def _rows_from_payload(payload: Any) -> list[dict]:
    """Defensively extract the announcement list from an annList response.

    The SZSE response shape is undocumented; check the known keys in order.
    """
    if isinstance(payload, dict):
        for key in ("result", "announcements", "data", "list"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
    if isinstance(payload, list):
        return payload
    return []


def list_szse_filings(
    stock_code: str,
    *,
    title: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    """List SZSE disclosures for a company.

    Args:
        stock_code: 6-digit SZSE ticker.
        title: optional title-substring filter (e.g. "年度报告").
        year: optional fiscal-year filter (publish-date window + title year).
        limit: max rows to return.

    Returns a list of ``{announcement_id, title, form, published, pdf_url,
    stock_code, source}``. Never raises on a missing company / empty result -
    returns ``[]``.  # undocumented - verify live: annList
    """
    code = (stock_code or "").strip()
    if not _is_szse_code(code):
        return []
    page_size = max(1, min(int(limit) * 2 + 10, 50))
    se_date: list[str] = []
    if year is not None:
        se_date = [f"{year}-01-01", f"{year + 1}-12-31"]
    body: dict[str, Any] = {
        "seDate": se_date,
        "stock": [{"stockCode": code}],
        "channelCode": ["fixed_disc"],
        "pageSize": page_size,
        "pageNum": 1,
    }
    try:
        payload = _post_json("/api/disc/announcement/annList", body)
    except Exception:
        return []
    results = [_map_announcement(r, code) for r in _rows_from_payload(payload) if isinstance(r, dict)]
    if title:
        results = [r for r in results if title in (r.get("title") or "")]
    if year is not None:
        results = [r for r in results if str(year) in (r.get("title") or "")]
    return results[:limit]


def get_szse_annual_report_filing(stock_code: str, year: int) -> Optional[dict]:
    """Pick the FY{year} annual-report filing from the SZSE disclosure list."""
    rows = list_szse_filings(stock_code, title="年度报告", year=year, limit=10)
    for r in rows:
        if r.get("pdf_url") and "年度报告" in (r.get("title") or ""):
            return r
    for r in rows:
        if r.get("pdf_url"):
            return r
    return None if not rows else rows[0]


# ── 互动易 (investor Q&A, hosted on irm.cninfo.com.cn) ────────────


def get_szse_interaction(stock_code: str, *, limit: int = 20) -> dict:
    """Fetch 互动易 investor Q&A for a SZSE-listed company.

    Returns ``{stock_code, source, questions: [...]}`` or ``{..., error}``.
    # undocumented - verify live: irm.cninfo.com.cn/ircs interaction API
    """
    code = (stock_code or "").strip()
    if not _is_szse_code(code):
        return {"stock_code": code, "source": "irm-cninfo", "error": "not a SZSE code"}
    page_size = max(1, min(int(limit), 50))
    data = {"stockCode": code, "pageNo": "1", "pageSize": str(page_size)}
    try:
        payload = _interaction_post("/ircs/interaction/queryQuestionAndReplyLast", data)
    except Exception as e:  # noqa: BLE001 - miss-tolerant
        return {"stock_code": code, "source": "irm-cninfo", "error": f"{type(e).__name__}: {e}"}

    questions = []
    rows = _rows_from_payload(payload)
    for r in rows:
        if not isinstance(r, dict):
            continue
        questions.append({
            "question": r.get("question") or r.get("content") or r.get("title") or "",
            "answer": r.get("answer") or r.get("reply") or r.get("replyContent") or "",
            "questioner": r.get("questioner") or r.get("askedBy") or "",
            "asked": r.get("asked") or r.get("questionDate") or "",
            "answered": r.get("answered") or r.get("replyDate") or "",
        })
    return {"stock_code": code, "source": "irm-cninfo", "questions": questions[:limit]}


# ── health ────────────────────────────────────────────────────────


def ping() -> dict:
    """Lightweight liveness probe for the SZSE disclosure host. Never raises."""
    url = _BASE + "/api/disc/announcement/annList"
    client = _client()
    try:
        resp = U.request_retry(
            client, "POST", "/api/disc/announcement/annList",
            json={"seDate": [], "stock": [{"stockCode": "000001"}],
                  "channelCode": ["fixed_disc"], "pageSize": 1, "pageNum": 1},
            headers={"Content-Type": "application/json"},
        )
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "url": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status_code": None, "url": url, "error": f"{type(e).__name__}: {e}"}
    finally:
        client.close()
