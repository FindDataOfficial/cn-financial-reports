"""BSE (北京证券交易所, www.bse.cn) HTTP client.

A direct, primary-source path to BSE-listed company disclosures. BSE is newer
than SSE/SZSE and its own JSON API is thinner/less documented; BSE-listed
companies' disclosures are also published on CNINFO (column ``bj``). So
``list_bse_filings`` tries the BSE-native endpoint first (best-effort
enrichment) and falls back to CNINFO, tagging each row with ``source``:
``"bse"`` or ``"cninfo"``. The CNINFO fallback is the reliable production path.

Endpoints (undocumented - marked ``# undocumented - verify live``):

  www.bse.cn/api/...                          - BSE-native disclosure (UNVERIFIED)
  cninfo.com.cn (via cninfo_client)           - reliable fallback

Every call goes through ``official_client_utils`` (``trust_env=False`` +
429/5xx retry/backoff). Mock-friendly: tests patch ``_post_json`` (BSE-native)
and ``cninfo_client`` (fallback). Company resolution is code-based and local:
BSE codes are 430xxx / 83xxxx / 87xxxx / 88xxxx / 920xxx.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

import official_client_utils as U

_BASE = "http://www.bse.cn"
_TIMEOUT = 30.0
_SLEEP = U.SLEEP
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# BSE 6-digit code prefixes: 430xxx (NEEQ->BSE), 83xxxx, 87xxxx, 88xxxx, 920xxx.
_BSE_PREFIX2 = ("43", "83", "87", "88")
_BSE_PREFIX3 = ("920",)


def _client() -> httpx.Client:
    """Per-call httpx client. Tests patch this to inject a mock."""
    return U.make_client(
        base_url=_BASE,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "http://www.bse.cn/disclosureInfoAnnouncement.html",
            "Origin": "http://www.bse.cn",
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


# ── company resolution (code-based, local) ────────────────────────


def _is_bse_code(code: str) -> bool:
    if not (code and code.isdigit() and len(code) == 6):
        return False
    return code[:2] in _BSE_PREFIX2 or code[:3] in _BSE_PREFIX3


def lookup_bse_company(ticker_or_name: str) -> Optional[dict]:
    """Resolve a BSE-listed company by 6-digit ticker.

    Returns ``{stock_code, exchange, source, name}`` for a valid BSE code, or
    ``None`` otherwise. Pure-local, no network call.
    """
    code = (ticker_or_name or "").strip()
    if not _is_bse_code(code):
        return None
    return {"stock_code": code, "exchange": "bse", "source": "bse", "name": ""}


# ── disclosure listing (BSE-native + CNINFO fallback) ─────────────


def _form_from_title(title: str) -> str:
    if not title:
        return ""
    for form in ("半年度报告", "第一季度报告", "第三季度报告", "年度报告", "招股说明书"):
        if form in title:
            return form
    return ""


def _map_bse_row(row: dict, stock_code: str) -> dict:
    url = row.get("attachPath") or row.get("adjunctUrl") or row.get("url") or ""
    if url and not url.startswith("http"):
        url = _BASE + "/" + url.lstrip("/")
    return {
        "announcement_id": str(row.get("id") or row.get("announcementId") or ""),
        "title": row.get("title") or row.get("announcementTitle") or "",
        "form": _form_from_title(row.get("title") or ""),
        "published": (row.get("publishDate") or row.get("seDate") or row.get("noticeDate") or "")[:10],
        "pdf_url": url,
        "stock_code": stock_code,
        "source": "bse",
    }


def _bse_native_filings(
    stock_code: str, *, title: Optional[str], year: Optional[int], limit: int,
) -> list[dict]:
    """Best-effort BSE-native disclosure query. Returns [] on any failure.

    # undocumented - UNVERIFIED: the BSE JSON disclosure endpoint shape is not
    # confidently known; the CNINFO fallback is the reliable path. This exists
    # so a working BSE-native endpoint can be wired in without changing callers.
    """
    page_size = max(1, min(int(limit) * 2 + 10, 50))
    body: dict[str, Any] = {
        "stockCode": stock_code,
        "pageSize": page_size,
        "pageNum": 1,
    }
    if year is not None:
        body["beginDate"] = f"{year}-01-01"
        body["endDate"] = f"{year + 1}-12-31"
    if title:
        body["title"] = title
    try:
        payload = _post_json("/api/disclosure/announcementList", body)
    except Exception:
        return []
    rows = []
    if isinstance(payload, dict):
        for key in ("result", "announcements", "data", "list"):
            r = payload.get(key)
            if isinstance(r, list):
                rows = r
                break
    elif isinstance(payload, list):
        rows = payload
    results = [_map_bse_row(r, stock_code) for r in rows if isinstance(r, dict)]
    if title:
        results = [r for r in results if title in (r.get("title") or "")]
    if year is not None:
        results = [r for r in results if str(year) in (r.get("title") or "")]
    return results[:limit]


def _cninfo_fallback_filings(
    stock_code: str, *, title: Optional[str], year: Optional[int], limit: int,
) -> list[dict]:
    """Reliable fallback: BSE disclosures on CNINFO (column ``bj``)."""
    import cninfo_client

    company = cninfo_client.lookup_company(stock_code)
    if not company:
        return []
    rows = cninfo_client.query_announcements(
        company["stock_code"], company["org_id"],
        form=title, year=year, limit=limit,
    )
    # Tag CNINFO-served rows so callers know the source.
    for r in rows:
        r["source"] = "cninfo"
    return rows


def list_bse_filings(
    stock_code: str,
    *,
    title: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    """List BSE disclosures for a company, with CNINFO cross-reference fallback.

    Tries the BSE-native endpoint first (rows tagged ``source: "bse"``); if it
    returns nothing, falls back to CNINFO (rows tagged ``source: "cninfo"``).

    Args:
        stock_code: 6-digit BSE ticker.
        title: optional title-substring filter (e.g. "年度报告").
        year: optional fiscal-year filter.
        limit: max rows to return.

    Returns a list of ``{announcement_id, title, form, published, pdf_url,
    stock_code, source}``. Never raises on a missing company / empty result -
    returns ``[]``.
    """
    code = (stock_code or "").strip()
    if not _is_bse_code(code):
        return []
    rows = _bse_native_filings(code, title=title, year=year, limit=limit)
    if not rows:
        rows = _cninfo_fallback_filings(code, title=title, year=year, limit=limit)
    return rows


def get_bse_annual_report_filing(stock_code: str, year: int) -> Optional[dict]:
    """Pick the FY{year} annual-report filing (BSE-native or CNINFO fallback)."""
    rows = list_bse_filings(stock_code, title="年度报告", year=year, limit=10)
    for r in rows:
        if r.get("pdf_url") and "年度报告" in (r.get("title") or ""):
            return r
    for r in rows:
        if r.get("pdf_url"):
            return r
    return None if not rows else rows[0]


# ── health ────────────────────────────────────────────────────────


def ping() -> dict:
    """Lightweight liveness probe for the BSE host. Never raises."""
    url = _BASE + "/api/disclosure/announcementList"
    client = _client()
    try:
        resp = U.request_retry(
            client, "POST", "/api/disclosure/announcementList",
            json={"stockCode": "920002", "pageSize": 1, "pageNum": 1},
            headers={"Content-Type": "application/json"},
        )
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "url": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status_code": None, "url": url, "error": f"{type(e).__name__}: {e}"}
    finally:
        client.close()
