"""Tests for csrc_client (CSRC / 证监会 official-website datasource).

Network is fully mocked via ``_fetch_html``. HTML fixtures under
``test_fixtures/csrc/`` document the ASSUMED page structure (CSRC's site is
HTML-driven and undocumented - see csrc_client docstring).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import csrc_client
import cnreport_tools as T

_FIX = Path(__file__).resolve().parent / "test_fixtures" / "csrc"


def _read(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def _patch_html(monkeypatch, mapping=None, raises=False):
    mapping = mapping or {}

    def fake_fetch(url, *, params=None):
        if raises:
            raise RuntimeError("boom")
        for key, html in mapping.items():
            if csrc_client._URLS[key] in url or url in csrc_client._URLS[key] or url == csrc_client._URLS[key]:
                return html
        return mapping.get("_default", "")

    monkeypatch.setattr(csrc_client, "_fetch_html", fake_fetch)


# ── announcement listing ──────────────────────────────────────────


def test_list_csrc_filings_parses_list(monkeypatch):
    _patch_html(monkeypatch, {"filings": _read("filings.html")})
    rows = csrc_client.list_csrc_filings(limit=10)
    assert len(rows) == 3
    r0 = rows[0]
    assert "反馈意见" in r0["title"]
    assert r0["published"] == "2024-04-02"
    assert r0["url"] == "http://www.csrc.gov.cn/pub/newsite/202404/1234.html"
    assert r0["source"] == "csrc"
    # full-URL href passed through unchanged
    assert rows[2]["url"] == "http://www.csrc.gov.cn/pub/newsite/202402/1232.html"


def test_list_csrc_filings_date_filter(monkeypatch):
    _patch_html(monkeypatch, {"filings": _read("filings.html")})
    rows = csrc_client.list_csrc_filings(begin_date="2024-03-01", limit=10)
    assert len(rows) == 2
    assert all(r["published"] >= "2024-03-01" for r in rows)


def test_list_csrc_filings_network_error_returns_empty(monkeypatch):
    _patch_html(monkeypatch, raises=True)
    assert csrc_client.list_csrc_filings() == []


# ── review status ─────────────────────────────────────────────────


def test_get_csrc_ipo_review_match(monkeypatch):
    _patch_html(monkeypatch, {"ipo_review": _read("review.html")})
    r = csrc_client.get_csrc_ipo_review("贵州茅台")
    assert r["source"] == "csrc"
    assert r["fields"]["审核状态"] == "已通过"
    assert r["fields"]["结果"] == "同意注册"


def test_get_csrc_ipo_review_no_match(monkeypatch):
    _patch_html(monkeypatch, {"ipo_review": _read("review.html")})
    r = csrc_client.get_csrc_ipo_review("不存在的公司")
    assert "error" in r and r["available"] == 2


def test_get_csrc_merger_review_match(monkeypatch):
    _patch_html(monkeypatch, {"merger_review": _read("review.html")})
    r = csrc_client.get_csrc_merger_review("某科技股份公司")
    assert r["fields"]["审核状态"] == "反馈中"


def test_get_csrc_review_no_table(monkeypatch):
    _patch_html(monkeypatch, {"_default": "<html></html>"})
    r = csrc_client.get_csrc_ipo_review("贵州茅台")
    assert "error" in r


# ── enforcement ───────────────────────────────────────────────────


def test_list_csrc_enforcement(monkeypatch):
    _patch_html(monkeypatch, {"enforcement": _read("enforcement.html")})
    rows = csrc_client.list_csrc_enforcement(limit=10)
    assert len(rows) == 2
    assert "行政处罚" in rows[0]["title"]
    assert rows[0]["source"] == "csrc"


def test_list_csrc_enforcement_network_error(monkeypatch):
    _patch_html(monkeypatch, raises=True)
    assert csrc_client.list_csrc_enforcement() == []


# ── ping never raises ─────────────────────────────────────────────


def test_ping_never_raises(monkeypatch):
    monkeypatch.setattr(csrc_client.U, "request_retry", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    r = csrc_client.ping()
    assert r["ok"] is False and "error" in r


# ── tool layer ────────────────────────────────────────────────────


def test_tool_list_csrc_filings(monkeypatch):
    _patch_html(monkeypatch, {"filings": _read("filings.html")})
    r = T.list_csrc_filings(limit=10)
    assert isinstance(r, list) and len(r) == 3 and r[0]["source"] == "csrc"


def test_tool_get_csrc_ipo_review(monkeypatch):
    _patch_html(monkeypatch, {"ipo_review": _read("review.html")})
    r = T.get_csrc_ipo_review("贵州茅台")
    assert r["fields"]["审核状态"] == "已通过"


def test_tool_list_csrc_enforcement(monkeypatch):
    _patch_html(monkeypatch, {"enforcement": _read("enforcement.html")})
    r = T.list_csrc_enforcement(limit=10)
    assert isinstance(r, list) and len(r) == 2
