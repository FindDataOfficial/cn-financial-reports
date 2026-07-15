"""Tests for sse_client (SSE / 上交所 official-website datasource).

Network is fully mocked: ``_post_form`` (disclosure listing) and
``_interaction_post`` (上证e互动) are the single chokepoints, patched per test.
Fixtures under ``test_fixtures/sse/`` document the ASSUMED endpoint contract
(endpoints are undocumented - see sse_client docstring).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sse_client
import cnreport_tools as T

_FIX = Path(__file__).resolve().parent / "test_fixtures" / "sse"


def _load(name: str):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


# ── _unwrap_jsonp ─────────────────────────────────────────────────


def test_unwrap_jsonp_raw_and_wrapped():
    assert sse_client._unwrap_jsonp('{"a": 1}') == {"a": 1}
    assert sse_client._unwrap_jsonp('jsonpCallback({"a": 1})') == {"a": 1}
    assert sse_client._unwrap_jsonp('jsonpCallback123({"a": 1});') == {"a": 1}


# ── company resolution (code-based, local) ────────────────────────


def test_lookup_sse_company_by_code():
    co = sse_client.lookup_sse_company("600519")
    assert co == {"stock_code": "600519", "exchange": "sse", "source": "sse", "name": ""}


@pytest.mark.parametrize("bad", ["000001", "00700", "830799", "60051", "茅台", ""])
def test_lookup_sse_company_rejects_non_sse(bad):
    assert sse_client.lookup_sse_company(bad) is None


# ── disclosure listing ────────────────────────────────────────────


def _patch_filings(monkeypatch, payload=None, raises=False):
    base_payload = payload if payload is not None else _load("bulletin.json")

    def fake_post(path, data, *, base=sse_client._BASE):
        if raises:
            raise RuntimeError("boom")
        if not isinstance(base_payload, dict):
            return base_payload
        result = base_payload.get("result", [])
        # Simulate the SSE server-side title-substring filter.
        title = (data or {}).get("title", "")
        if title:
            result = [r for r in result if title in (r.get("BULLETIN_TITLE") or "")]
        return {**base_payload, "result": result}

    monkeypatch.setattr(sse_client, "_post_form", fake_post)


def test_list_sse_filings_maps_rows(monkeypatch):
    _patch_filings(monkeypatch)
    rows = sse_client.list_sse_filings("600519", limit=10)
    assert len(rows) == 2
    annual = rows[0]
    assert annual["title"] == "贵州茅台2023年年度报告"
    assert annual["form"] == "年度报告"
    assert annual["published"] == "2024-04-02"
    assert annual["pdf_url"].startswith("http://static.sse.com.cn/")
    assert annual["stock_code"] == "600519"
    assert annual["source"] == "sse"
    # full-URL row passed through unchanged
    assert rows[1]["pdf_url"] == "http://static.sse.com.cn/disclosure/bulletin/2023-10-25/1220000111.pdf"


def test_list_sse_filings_year_filter(monkeypatch):
    _patch_filings(monkeypatch)
    rows = sse_client.list_sse_filings("600519", year=2023, limit=10)
    # Both fixture reports are FY2023 (annual + Q3); year filter keeps both,
    # matching cninfo_client's title-contains-year behavior.
    assert len(rows) == 2
    assert all("2023" in r["title"] for r in rows)


def test_list_sse_filings_title_filter(monkeypatch):
    _patch_filings(monkeypatch)
    rows = sse_client.list_sse_filings("600519", title="年度报告", limit=10)
    assert len(rows) == 1
    assert "年度报告" in rows[0]["title"]


def test_list_sse_filings_non_sse_code_returns_empty(monkeypatch):
    _patch_filings(monkeypatch)
    assert sse_client.list_sse_filings("000001") == []


def test_list_sse_filings_network_error_returns_empty(monkeypatch):
    _patch_filings(monkeypatch, raises=True)
    assert sse_client.list_sse_filings("600519") == []


def test_get_sse_annual_report_filing(monkeypatch):
    _patch_filings(monkeypatch)
    f = sse_client.get_sse_annual_report_filing("600519", 2023)
    assert f and f["pdf_url"].startswith("http://static.sse.com.cn/")
    assert "年度报告" in f["title"]


# ── 上证e互动 ─────────────────────────────────────────────────────


def _patch_interaction(monkeypatch, payload=None, raises=False):
    def fake_post(path, data):
        if raises:
            raise RuntimeError("boom")
        return payload if payload is not None else _load("interaction.json")
    monkeypatch.setattr(sse_client, "_interaction_post", fake_post)


def test_get_sse_interaction(monkeypatch):
    _patch_interaction(monkeypatch)
    r = sse_client.get_sse_interaction("600519", limit=5)
    assert r["source"] == "sseinfo"
    assert r["stock_code"] == "600519"
    assert len(r["questions"]) == 2
    assert r["questions"][0]["question"] == "公司未来分红规划?"
    assert r["questions"][0]["answer"]


def test_get_sse_interaction_error_is_miss_tolerant(monkeypatch):
    _patch_interaction(monkeypatch, raises=True)
    r = sse_client.get_sse_interaction("600519")
    assert "error" in r and r["source"] == "sseinfo"


def test_get_sse_interaction_non_sse_code(monkeypatch):
    _patch_interaction(monkeypatch)
    r = sse_client.get_sse_interaction("000001")
    assert "error" in r


# ── ping never raises ─────────────────────────────────────────────


def test_ping_never_raises(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("offline")
    monkeypatch.setattr(sse_client.U, "request_retry", boom)
    r = sse_client.ping()
    assert r["ok"] is False and "error" in r


# ── tool layer (cnreport_tools @ _tool_safe wrappers) ─────────────


def test_tool_get_sse_company(monkeypatch):
    assert T.get_sse_company("600519")["stock_code"] == "600519"
    err = T.get_sse_company("茅台")
    assert "error" in err


def test_tool_list_sse_filings(monkeypatch):
    _patch_filings(monkeypatch)
    r = T.list_sse_filings("600519", year=2023, limit=10)
    assert isinstance(r, list) and r and r[0]["source"] == "sse"
    err = T.list_sse_filings("000001")
    assert isinstance(err, dict) and "error" in err


def test_tool_get_sse_section(monkeypatch):
    _patch_filings(monkeypatch)
    monkeypatch.setattr(
        sse_client, "get_sse_annual_report_filing",
        lambda code, year: {"announcement_id": "1219730876",
                            "pdf_url": "http://static.sse.com.cn/x.pdf"},
    )
    text = (
        "第三节 管理层讨论与分析 ......... 12\n"
        "正文开始\n第三节 管理层讨论与分析\n营业收入增长。\n第四节 公司治理\n治理完善。\n"
    )
    import report_cache
    monkeypatch.setattr(
        report_cache, "get_or_fetch",
        lambda *a, **k: (text, {}),
    )
    r = T.get_sse_section("600519", 2023, "管理层讨论与分析")
    assert "error" not in r, r
    assert "营业收入增长" in r["text"]
    assert r["pdf_url"] == "http://static.sse.com.cn/x.pdf"
    assert r["stock_code"] == "600519"


def test_tool_get_sse_interaction(monkeypatch):
    _patch_interaction(monkeypatch)
    r = T.get_sse_interaction("600519", limit=5)
    assert r["source"] == "sseinfo" and len(r["questions"]) == 2
