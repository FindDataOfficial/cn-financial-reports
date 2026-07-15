"""Tests for szse_client (SZSE / 深交所 official-website datasource).

Network is fully mocked: ``_post_json`` (disclosure listing) and
``_interaction_post`` (互动易) are the single chokepoints. The client filters
title/year post-hoc, so the mock returns the full fixture. Fixtures under
``test_fixtures/szse/`` document the ASSUMED endpoint contract (undocumented).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import szse_client
import cnreport_tools as T

_FIX = Path(__file__).resolve().parent / "test_fixtures" / "szse"


def _load(name: str):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


# ── company resolution ────────────────────────────────────────────


def test_lookup_szse_company_by_code():
    co = szse_client.lookup_szse_company("000001")
    assert co == {"stock_code": "000001", "exchange": "szse", "source": "szse", "name": ""}


@pytest.mark.parametrize("bad", ["600519", "00700", "830799", "00001", "平安银行", ""])
def test_lookup_szse_company_rejects_non_szse(bad):
    assert szse_client.lookup_szse_company(bad) is None


# ── disclosure listing ────────────────────────────────────────────


def _patch_filings(monkeypatch, payload=None, raises=False):
    base = payload if payload is not None else _load("annlist.json")

    def fake_post(path, body):
        if raises:
            raise RuntimeError("boom")
        return base
    monkeypatch.setattr(szse_client, "_post_json", fake_post)


def test_list_szse_filings_maps_rows(monkeypatch):
    _patch_filings(monkeypatch)
    rows = szse_client.list_szse_filings("000001", limit=10)
    assert len(rows) == 2
    annual = rows[0]
    assert annual["title"] == "平安银行2023年年度报告"
    assert annual["form"] == "年度报告"
    assert annual["published"] == "2024-03-15"
    assert annual["pdf_url"] == "http://www.szse.cn/api/disc/info/ann/000001-2024.pdf"
    assert annual["stock_code"] == "000001"
    assert annual["source"] == "szse"
    # full-URL attachPath passed through unchanged
    assert rows[1]["pdf_url"] == "http://www.szse.cn/api/disc/info/ann/000001-2023q3.pdf"


def test_list_szse_filings_year_filter(monkeypatch):
    _patch_filings(monkeypatch)
    rows = szse_client.list_szse_filings("000001", year=2023, limit=10)
    assert len(rows) == 2
    assert all("2023" in r["title"] for r in rows)


def test_list_szse_filings_title_filter(monkeypatch):
    _patch_filings(monkeypatch)
    rows = szse_client.list_szse_filings("000001", title="年度报告", limit=10)
    assert len(rows) == 1
    assert "年度报告" in rows[0]["title"]


def test_list_szse_filings_non_szse_code_returns_empty(monkeypatch):
    _patch_filings(monkeypatch)
    assert szse_client.list_szse_filings("600519") == []


def test_list_szse_filings_network_error_returns_empty(monkeypatch):
    _patch_filings(monkeypatch, raises=True)
    assert szse_client.list_szse_filings("000001") == []


def test_get_szse_annual_report_filing(monkeypatch):
    _patch_filings(monkeypatch)
    f = szse_client.get_szse_annual_report_filing("000001", 2023)
    assert f and f["pdf_url"].startswith("http://www.szse.cn/")
    assert "年度报告" in f["title"]


# ── 互动易 ────────────────────────────────────────────────────────


def _patch_interaction(monkeypatch, payload=None, raises=False):
    def fake_post(path, data):
        if raises:
            raise RuntimeError("boom")
        return payload if payload is not None else _load("interaction.json")
    monkeypatch.setattr(szse_client, "_interaction_post", fake_post)


def test_get_szse_interaction(monkeypatch):
    _patch_interaction(monkeypatch)
    r = szse_client.get_szse_interaction("000001", limit=5)
    assert r["source"] == "irm-cninfo"
    assert r["stock_code"] == "000001"
    assert len(r["questions"]) == 1
    assert r["questions"][0]["question"] == "未来分红计划?"


def test_get_szse_interaction_error_is_miss_tolerant(monkeypatch):
    _patch_interaction(monkeypatch, raises=True)
    r = szse_client.get_szse_interaction("000001")
    assert "error" in r and r["source"] == "irm-cninfo"


def test_get_szse_interaction_non_szse_code(monkeypatch):
    _patch_interaction(monkeypatch)
    assert "error" in szse_client.get_szse_interaction("600519")


# ── ping never raises ─────────────────────────────────────────────


def test_ping_never_raises(monkeypatch):
    monkeypatch.setattr(szse_client.U, "request_retry", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    r = szse_client.ping()
    assert r["ok"] is False and "error" in r


# ── tool layer ────────────────────────────────────────────────────


def test_tool_get_szse_company(monkeypatch):
    assert T.get_szse_company("000001")["stock_code"] == "000001"
    assert "error" in T.get_szse_company("茅台")


def test_tool_list_szse_filings(monkeypatch):
    _patch_filings(monkeypatch)
    r = T.list_szse_filings("000001", year=2023, limit=10)
    assert isinstance(r, list) and r and r[0]["source"] == "szse"
    err = T.list_szse_filings("600519")
    assert isinstance(err, dict) and "error" in err


def test_tool_get_szse_section(monkeypatch):
    _patch_filings(monkeypatch)
    monkeypatch.setattr(
        szse_client, "get_szse_annual_report_filing",
        lambda code, year: {"announcement_id": "1", "pdf_url": "http://www.szse.cn/x.pdf"},
    )
    text = (
        "第三节 管理层讨论与分析 ......... 12\n"
        "正文开始\n第三节 管理层讨论与分析\n净利润增长。\n第四节 公司治理\n治理完善。\n"
    )
    import report_cache
    monkeypatch.setattr(report_cache, "get_or_fetch", lambda *a, **k: (text, {}))
    r = T.get_szse_section("000001", 2023, "管理层讨论与分析")
    assert "error" not in r, r
    assert "净利润增长" in r["text"]
    assert r["stock_code"] == "000001"


def test_tool_get_szse_interaction(monkeypatch):
    _patch_interaction(monkeypatch)
    r = T.get_szse_interaction("000001", limit=5)
    assert r["source"] == "irm-cninfo" and len(r["questions"]) == 1
