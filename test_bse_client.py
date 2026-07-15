"""Tests for bse_client (BSE / 北交所 official-website datasource).

Covers both spec scenarios: BSE-native disclosure (``source: "bse"``) and the
CNINFO cross-reference fallback (``source: "cninfo"``). Network is fully mocked
via ``_post_json`` (BSE-native) and ``cninfo_client`` (fallback).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import bse_client
import cninfo_client
import cnreport_tools as T

_FIX = Path(__file__).resolve().parent / "test_fixtures" / "bse"


def _load(name: str):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


# ── company resolution ────────────────────────────────────────────


@pytest.mark.parametrize("code", ["920002", "430045", "835185", "830799", "870866"])
def test_lookup_bse_company_by_code(code):
    co = bse_client.lookup_bse_company(code)
    assert co == {"stock_code": code, "exchange": "bse", "source": "bse", "name": ""}


@pytest.mark.parametrize("bad", ["600519", "000001", "00700", "83518", "茅台", ""])
def test_lookup_bse_company_rejects_non_bse(bad):
    assert bse_client.lookup_bse_company(bad) is None


# ── disclosure listing: BSE-native ────────────────────────────────


def _patch_bse_native(monkeypatch, payload=None, raises=False):
    base = payload if payload is not None else _load("annlist.json")

    def fake_post(path, body):
        if raises:
            raise RuntimeError("boom")
        return base
    monkeypatch.setattr(bse_client, "_post_json", fake_post)


def _disable_cninfo_fallback(monkeypatch):
    """Ensure the fallback isn't accidentally hit during BSE-native tests."""
    monkeypatch.setattr(bse_client, "_cninfo_fallback_filings", lambda *a, **k: [])


def test_list_bse_filings_served_from_bse(monkeypatch):
    _patch_bse_native(monkeypatch)
    _disable_cninfo_fallback(monkeypatch)
    rows = bse_client.list_bse_filings("835185", limit=10)
    assert len(rows) == 2
    annual = rows[0]
    assert annual["title"] == "贝特瑞2023年年度报告"
    assert annual["form"] == "年度报告"
    assert annual["published"] == "2024-04-15"
    assert annual["pdf_url"] == "http://www.bse.cn/api/disc/info/835185-2024.pdf"
    assert annual["source"] == "bse"
    assert rows[1]["pdf_url"] == "http://www.bse.cn/api/disc/info/835185-2023q3.pdf"


def test_list_bse_filings_bse_title_and_year_filter(monkeypatch):
    _patch_bse_native(monkeypatch)
    _disable_cninfo_fallback(monkeypatch)
    rows = bse_client.list_bse_filings("835185", title="年度报告", year=2023, limit=10)
    assert len(rows) == 1
    assert "年度报告" in rows[0]["title"] and rows[0]["source"] == "bse"


# ── disclosure listing: CNINFO fallback ───────────────────────────


def _patch_cninfo_fallback(monkeypatch, rows):
    monkeypatch.setattr(
        cninfo_client, "lookup_company",
        lambda code: {"stock_code": code, "org_id": "gsbj0835185", "exchange": "bse"},
    )
    monkeypatch.setattr(cninfo_client, "query_announcements", lambda *a, **k: rows)


def test_list_bse_filings_falls_back_to_cninfo(monkeypatch):
    # BSE-native returns nothing (endpoint failure) -> CNINFO fallback kicks in.
    _patch_bse_native(monkeypatch, raises=True)
    cninfo_rows = [
        {"announcement_id": "9", "title": "贝特瑞2023年年度报告", "form": "年度报告",
         "published": "2024-04-15", "pdf_url": "http://static.cninfo.com.cn/finalpage/2024-04-15/9.PDF",
         "stock_code": "835185", "company_name": "贝特瑞"},
    ]
    _patch_cninfo_fallback(monkeypatch, cninfo_rows)

    rows = bse_client.list_bse_filings("835185", title="年度报告", year=2023, limit=10)
    assert len(rows) == 1
    assert rows[0]["source"] == "cninfo"
    assert rows[0]["pdf_url"].startswith("http://static.cninfo.com.cn/")


def test_list_bse_filings_non_bse_code_returns_empty(monkeypatch):
    _patch_bse_native(monkeypatch)
    assert bse_client.list_bse_filings("600519") == []


def test_list_bse_filings_both_paths_empty(monkeypatch):
    _patch_bse_native(monkeypatch, raises=True)
    _patch_cninfo_fallback(monkeypatch, [])
    assert bse_client.list_bse_filings("835185") == []


def test_get_bse_annual_report_filing(monkeypatch):
    _patch_bse_native(monkeypatch)
    _disable_cninfo_fallback(monkeypatch)
    f = bse_client.get_bse_annual_report_filing("835185", 2023)
    assert f and f["pdf_url"].startswith("http://www.bse.cn/")
    assert "年度报告" in f["title"]


# ── ping never raises ─────────────────────────────────────────────


def test_ping_never_raises(monkeypatch):
    monkeypatch.setattr(bse_client.U, "request_retry", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    r = bse_client.ping()
    assert r["ok"] is False and "error" in r


# ── tool layer ────────────────────────────────────────────────────


def test_tool_get_bse_company(monkeypatch):
    assert T.get_bse_company("835185")["stock_code"] == "835185"
    assert "error" in T.get_bse_company("茅台")


def test_tool_list_bse_filings_bse(monkeypatch):
    _patch_bse_native(monkeypatch)
    _disable_cninfo_fallback(monkeypatch)
    r = T.list_bse_filings("835185", year=2023, limit=10)
    assert isinstance(r, list) and r and r[0]["source"] == "bse"


def test_tool_list_bse_filings_cninfo_fallback(monkeypatch):
    _patch_bse_native(monkeypatch, raises=True)
    _patch_cninfo_fallback(monkeypatch, [
        {"announcement_id": "9", "title": "贝特瑞2023年年度报告", "form": "年度报告",
         "published": "2024-04-15", "pdf_url": "http://static.cninfo.com.cn/x.PDF",
         "stock_code": "835185", "company_name": "贝特瑞"},
    ])
    r = T.list_bse_filings("835185", title="年度报告", year=2023, limit=10)
    assert isinstance(r, list) and r and r[0]["source"] == "cninfo"
    err = T.list_bse_filings("600519")
    assert isinstance(err, dict) and "error" in err


def test_tool_get_bse_section_carries_source(monkeypatch):
    _patch_bse_native(monkeypatch)
    _disable_cninfo_fallback(monkeypatch)
    monkeypatch.setattr(
        bse_client, "get_bse_annual_report_filing",
        lambda code, year: {"announcement_id": "101", "pdf_url": "http://www.bse.cn/x.pdf",
                            "source": "bse"},
    )
    text = (
        "第三节 管理层讨论与分析 ......... 12\n"
        "正文开始\n第三节 管理层讨论与分析\n营收增长。\n第四节 公司治理\n治理完善。\n"
    )
    import report_cache
    monkeypatch.setattr(report_cache, "get_or_fetch", lambda *a, **k: (text, {}))
    r = T.get_bse_section("835185", 2023, "管理层讨论与分析")
    assert "error" not in r, r
    assert "营收增长" in r["text"]
    assert r["source"] == "bse"
    assert r["stock_code"] == "835185"
