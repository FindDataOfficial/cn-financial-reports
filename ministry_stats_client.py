"""Ministry-level department (部级部门) statistics client.

Exposes structured economic/financial statistics published by Chinese
ministry-level departments as queryable MCP tools - complementing
``fd-cn-gov`` (which catalog-scrapes ministry *document archives*) with
structured *data* queries.

Initial ministry set:

  nbs   国家统计局     (NBS)   - macro stats, JSON via data.stats.gov.cn/easyquery.htm
  mof   财政部         (MOF)   - fiscal, HTML tables
  pboc  中国人民银行   (PBoC)  - monetary, HTML tables
  safe  国家外汇管理局 (SAFE)  - FX/reserves, HTML tables
  gacc  海关总署       (GACC)  - trade, HTML tables
  nfra  国家金融监督管理总局 (NFRA) - banking/insurance, HTML tables

NBS has a (semi-documented) JSON API; the others publish HTML tables parsed
with ``lxml``. Every endpoint is marked ``# undocumented - verify live``.
Queries are memoized behind the TTL stat-cache (``official_client_utils``,
``.cache/stats/``). Ministry base URLs prefer ``fd-cn-gov``'s ``registry.json``
metadata when importable, falling back to hardcoded ``_MINISTRIES`` entries so
``fd-cn-report`` stays standalone. Mock-friendly: tests patch ``_fetch_json``
/ ``_fetch_html`` / ``_fdcn_gov_lookup``.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Optional

import httpx
from lxml import html as lxml_html

import official_client_utils as U

_TIMEOUT = 30.0
_SLEEP = U.SLEEP
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_NBS_BASE = "https://data.stats.gov.cn"

# Ministry registry. ``transport`` is "json" (NBS) or "html" (table scrape).
# ``stat_path`` is a best-guess path appended to ``base`` for the default stat
# page (undocumented - UNVERIFIED). ``ttl`` is the stat-cache TTL in seconds.
_MINISTRIES: dict[str, dict[str, Any]] = {
    "nbs": {"label": "国家统计局", "en": "NBS", "base": _NBS_BASE, "transport": "json",
            "stat_path": "/easyquery.htm", "ttl": 6 * 3600},
    "mof": {"label": "财政部", "en": "MOF", "base": "http://www.mof.gov.cn", "transport": "html",
            "stat_path": "/tongjizhibiao/", "ttl": 6 * 3600},
    "pboc": {"label": "中国人民银行", "en": "PBoC", "base": "http://www.pbc.gov.cn", "transport": "html",
             "stat_path": "/diaochatongjisi/116219/116319/index.html", "ttl": 6 * 3600},
    "safe": {"label": "国家外汇管理局", "en": "SAFE", "base": "https://www.safe.gov.cn", "transport": "html",
             "stat_path": "/safe/whsj/list.html", "ttl": 6 * 3600},
    "gacc": {"label": "海关总署", "en": "GACC", "base": "http://www.customs.gov.cn", "transport": "html",
             "stat_path": "/customs/302249/zfxxgjbgjk/", "ttl": 6 * 3600},
    "nfra": {"label": "国家金融监督管理总局", "en": "NFRA", "base": "https://www.nfra.gov.cn", "transport": "html",
             "stat_path": "/cn/cms/pages/", "ttl": 6 * 3600},
}

# fd-cn-gov covers MOF/PBC/SAFE as catalog scrapers; map our id -> its source-id prefix.
_FDCN_PREFIX = {"mof": "mof", "pboc": "pbc", "safe": "safe"}


def _client(base: str) -> httpx.Client:
    return U.make_client(
        base_url=base,
        headers={"User-Agent": _UA, "Accept": "text/html,application/json,*/*;q=0.8",
                 "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        timeout=_TIMEOUT,
    )


def _fetch_html(url: str) -> str:
    """GET ``url`` and return text. Errors raise; tests patch this."""
    client = _client(url)
    try:
        resp = U.request_retry(client, "GET", url)
        resp.raise_for_status()
        return resp.text
    finally:
        client.close()


def _fetch_json(url: str, params: Optional[dict] = None) -> Any:
    """GET ``url`` and return parsed JSON. Errors raise; tests patch this."""
    client = _client(url)
    try:
        resp = U.request_retry(client, "GET", url, params=params)
        resp.raise_for_status()
        return resp.json()
    finally:
        client.close()


# ── fd-cn-gov registry reuse (optional) ───────────────────────────


def _fdcn_gov_lookup(ministry_id: str) -> Optional[str]:
    """Best-effort: read fd-cn-gov's ``registry.json`` for a ministry base URL.

    Returns the URL or ``None`` (fd-cn-gov not installed / ministry not found).
    Never raises. Tests monkeypatch this to simulate fd-cn-gov availability.
    """
    prefix = _FDCN_PREFIX.get(ministry_id)
    if not prefix:
        return None  # nbs/gacc/nfra are not in fd-cn-gov
    try:
        spec = importlib.util.find_spec("fd_cn_gov")
        if spec is None or not spec.origin:
            return None
        reg_path = Path(spec.origin).resolve().parent / "registry" / "registry.json"
        if not reg_path.exists():
            return None
        data = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    for src in data.get("sources", []):
        if (src.get("id") or "").startswith(prefix + "_"):
            return src.get("url") or None
    return None


def _resolve_base(ministry_id: str) -> str:
    """Base URL for a ministry: fd-cn-gov registry if available, else hardcoded."""
    fallback = _MINISTRIES.get(ministry_id, {}).get("base", "")
    try:
        url = _fdcn_gov_lookup(ministry_id)
    except Exception:
        url = None
    return url or fallback


# ── registry listing ──────────────────────────────────────────────


def list_ministries() -> list[dict]:
    """Return the supported ministry set with metadata."""
    return [
        {"id": mid, "label": m["label"], "en": m["en"], "transport": m["transport"],
         "base": _resolve_base(mid)}
        for mid, m in _MINISTRIES.items()
    ]


# ── HTML table parsing (MOF/PBoC/SAFE/GACC/NFRA) ─────────────────


def _parse_html_tables(html_text: str, *, limit: int = 50) -> list[dict]:
    """Parse all ``<table>`` elements into ``{headers, rows}`` dicts.

    Returns ``[]`` on a malformed page. Defensive - never raises.
    """
    try:
        tree = lxml_html.fromstring(html_text)
    except Exception:
        return []
    tables: list[dict] = []
    for table in tree.xpath("//table"):
        rows = table.xpath(".//tr")
        if len(rows) < 2:
            continue
        headers = [(c.text_content() or "").strip() for c in rows[0].xpath(".//th | .//td")]
        table_rows: list[dict] = []
        for tr in rows[1:][:limit]:
            cells = [(td.text_content() or "").strip() for td in tr.xpath(".//td")]
            if not cells:
                continue
            if any(headers):
                table_rows.append({headers[i]: cells[i] for i in range(min(len(headers), len(cells)))})
            else:
                table_rows.append({f"col{i}": v for i, v in enumerate(cells)})
        if table_rows:
            tables.append({"headers": [h for h in headers if h], "rows": table_rows})
    return tables


def _ministry_stat_raw(ministry_id: str, meta: dict, url: str, limit: int) -> dict:
    try:
        html_text = _fetch_html(url)
    except Exception as e:  # noqa: BLE001 - miss-tolerant
        return {"ministry": ministry_id, "label": meta["label"], "source": ministry_id,
                "url": url, "error": f"{type(e).__name__}: {e}"}
    tables = _parse_html_tables(html_text, limit=limit)
    return {"ministry": ministry_id, "label": meta["label"], "source": ministry_id,
            "url": url, "tables": tables, "table_count": len(tables)}


def get_ministry_stat(
    ministry_id: str,
    *,
    url: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """Fetch a ministry's statistics page and parse its HTML tables.

    Args:
        ministry_id: one of nbs/mof/pboc/safe/gacc/nfra (nbs is better served
            by :func:`get_nbs_stat`).
        url: optional explicit stat-page URL (overrides the default).
        limit: max rows per table.

    Returns ``{ministry, label, source, url, tables, table_count}`` or
    ``{..., error}``. Cached behind the per-ministry TTL. Never raises.
    # undocumented - verify live: default stat_path per ministry.
    """
    meta = _MINISTRIES.get(ministry_id)
    if not meta:
        return {"ministry": ministry_id, "source": ministry_id, "error": "unknown ministry"}
    base = _resolve_base(ministry_id)
    target = url or (base + meta.get("stat_path", ""))
    key = U.stat_cache_key(ministry_id, target, limit)
    return U.cached_stat(key, meta.get("ttl", 3600),
                         lambda: _ministry_stat_raw(ministry_id, meta, target, limit))


# ── NBS (国家统计局) JSON query ───────────────────────────────────


def _nbs_stat_raw(indicator_code: str, dbcode: str) -> dict:
    params = {
        "m": "QueryData",
        "dbcode": dbcode,
        "rowcode": "zb",
        "colcode": "sj",
        "wds": "[]",
        "dfwds": json.dumps([{"wdcode": "zb", "valuecode": indicator_code}]),
    }
    try:
        payload = _fetch_json(_NBS_BASE + "/easyquery.htm", params)
    except Exception as e:  # noqa: BLE001
        return {"indicator": indicator_code, "source": "nbs", "dbcode": dbcode,
                "error": f"{type(e).__name__}: {e}"}
    rd = (payload or {}).get("returndata") or {}
    sj_nodes: dict[str, str] = {}
    for wn in rd.get("wdnodes", []):
        if wn.get("wdcode") == "sj":
            for n in wn.get("nodes", []):
                sj_nodes[n.get("code")] = n.get("cname") or n.get("code")
    series: dict[str, Any] = {}
    for dn in rd.get("datanodes", []) or []:
        data_list = (dn.get("data") or {}).get("data") or []
        if not data_list:
            continue
        value = data_list[0].get("data")
        period = ""
        for w in dn.get("wds", []) or []:
            if w.get("wdcode") == "sj":
                period = sj_nodes.get(w.get("valuecode"), w.get("valuecode"))
        if period:
            series[period] = value
    return {"indicator": indicator_code, "source": "nbs", "dbcode": dbcode, "data": series}


def get_nbs_stat(indicator_code: str, *, dbcode: str = "hgnd") -> dict:
    """Query an NBS (国家统计局) macro statistic by indicator code.

    ``dbcode`` defaults to ``hgnd`` (national annual). The NBS ``easyquery.htm``
    API is semi-documented - verify live. Returns ``{indicator, source, dbcode,
    data: {period: value}}`` or ``{..., error}``. Cached behind the NBS TTL.
    """
    key = U.stat_cache_key("nbs", indicator_code, dbcode)
    return U.cached_stat(key, _MINISTRIES["nbs"]["ttl"],
                         lambda: _nbs_stat_raw(indicator_code, dbcode))


# ── health ────────────────────────────────────────────────────────


def ping() -> dict:
    """Liveness probe for the NBS JSON host (representative for the module)."""
    url = _NBS_BASE + "/easyquery.htm"
    client = _client(_NBS_BASE)
    try:
        resp = U.request_retry(client, "GET", url,
                               params={"m": "getOtherWds", "dbcode": "hgnd", "rowcode": "zb"})
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "url": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status_code": None, "url": url, "error": f"{type(e).__name__}: {e}"}
    finally:
        client.close()
