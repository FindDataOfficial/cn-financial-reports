"""Tests for ministry_stats_client (部级部门 statistics).

Network is fully mocked via ``_fetch_json`` (NBS) and ``_fetch_html`` (HTML
ministries). Covers NBS JSON parsing, GACC HTML-table parsing, the TTL
stat-cache, and the optional fd-cn-gov registry reuse.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import ministry_stats_client as M
import cnreport_tools as T

_FIX = Path(__file__).resolve().parent / "test_fixtures" / "ministry"


def _read(name: str):
    p = _FIX / name
    return p.read_text(encoding="utf-8") if p.suffix == ".html" else json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture
def stat_cache(tmp_path, monkeypatch):
    """Isolate the stat-cache to a temp dir per test."""
    monkeypatch.setenv("CNREPORT_STAT_CACHE_DIR", str(tmp_path / "stats"))
    return tmp_path


# ── registry + fd-cn-gov reuse ────────────────────────────────────


def test_list_ministries_has_six():
    ministries = {m["id"]: m for m in M.list_ministries()}
    assert set(ministries) == {"nbs", "mof", "pboc", "safe", "gacc", "nfra"}
    assert ministries["nbs"]["transport"] == "json"
    assert ministries["gacc"]["transport"] == "html"


def test_resolve_base_fallback_without_fd_cn_gov(monkeypatch):
    # fd_cn_gov is not installed in the test env -> _fdcn_gov_lookup returns None.
    monkeypatch.setattr(M, "_fdcn_gov_lookup", lambda mid: None)
    assert M._resolve_base("nbs") == M._NBS_BASE
    assert M._resolve_base("mof") == M._MINISTRIES["mof"]["base"]


def test_resolve_base_uses_fd_cn_gov_when_available(monkeypatch):
    monkeypatch.setattr(M, "_fdcn_gov_lookup", lambda mid: "http://from-fdcn-gov/" if mid == "mof" else None)
    assert M._resolve_base("mof") == "http://from-fdcn-gov/"
    assert M._resolve_base("nbs") == M._NBS_BASE  # nbs not in fd-cn-gov


def test_fdcn_gov_lookup_returns_none_for_uncovered_ministries():
    # nbs/gacc/nfra are not in fd-cn-gov; never raises even if package absent.
    assert M._fdcn_gov_lookup("nbs") is None
    assert M._fdcn_gov_lookup("gacc") is None


# ── NBS JSON query ────────────────────────────────────────────────


def test_get_nbs_stat_parses_series(stat_cache, monkeypatch):
    calls = {"n": 0}

    def fake_fetch(url, params=None):
        calls["n"] += 1
        return _read("nbs_gdp.json")

    monkeypatch.setattr(M, "_fetch_json", fake_fetch)
    r = M.get_nbs_stat("A0201")
    assert r["source"] == "nbs"
    assert r["data"]["2023年"] == 1260582.1
    assert r["data"]["2022年"] == 1210207.2
    # stat-cache: second call must not re-fetch.
    r2 = M.get_nbs_stat("A0201")
    assert calls["n"] == 1
    assert r2["data"]["2023年"] == 1260582.1


def test_get_nbs_stat_network_error(stat_cache, monkeypatch):
    def boom(url, params=None):
        raise RuntimeError("offline")
    monkeypatch.setattr(M, "_fetch_json", boom)
    r = M.get_nbs_stat("A0201")
    assert "error" in r and r["source"] == "nbs"


# ── HTML ministry (GACC) ──────────────────────────────────────────


def test_get_ministry_stat_parses_html_tables(stat_cache, monkeypatch):
    monkeypatch.setattr(M, "_fetch_html", lambda url: _read("gacc_trade.html"))
    r = M.get_ministry_stat("gacc")
    assert r["source"] == "gacc"
    assert r["table_count"] == 1
    rows = r["tables"][0]["rows"]
    assert len(rows) == 2
    assert rows[0]["月份"] == "2024年1月"
    assert rows[0]["进出口(亿元)"] == "5643.5"


def test_get_ministry_stat_unknown_ministry(stat_cache):
    r = M.get_ministry_stat("xxx")
    assert "error" in r


def test_get_ministry_stat_network_error(stat_cache, monkeypatch):
    monkeypatch.setattr(M, "_fetch_html", lambda url: (_ for _ in ()).throw(RuntimeError("offline")))
    r = M.get_ministry_stat("gacc")
    assert "error" in r and r["source"] == "gacc"


def test_get_ministry_stat_uses_cache(stat_cache, monkeypatch):
    calls = {"n": 0}

    def fake_fetch(url):
        calls["n"] += 1
        return _read("gacc_trade.html")

    monkeypatch.setattr(M, "_fetch_html", fake_fetch)
    M.get_ministry_stat("gacc")
    M.get_ministry_stat("gacc")
    assert calls["n"] == 1


# ── ping never raises ─────────────────────────────────────────────


def test_ping_never_raises(monkeypatch):
    monkeypatch.setattr(M.U, "request_retry", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    r = M.ping()
    assert r["ok"] is False and "error" in r


# ── tool layer ────────────────────────────────────────────────────


def test_tool_list_ministries():
    r = T.list_ministries()
    assert isinstance(r, list) and len(r) == 6


def test_tool_get_nbs_stat(stat_cache, monkeypatch):
    monkeypatch.setattr(M, "_fetch_json", lambda url, params=None: _read("nbs_gdp.json"))
    r = T.get_nbs_stat("A0201")
    assert r["data"]["2023年"] == 1260582.1


def test_tool_get_ministry_stat(stat_cache, monkeypatch):
    monkeypatch.setattr(M, "_fetch_html", lambda url: _read("gacc_trade.html"))
    r = T.get_ministry_stat("gacc")
    assert r["table_count"] == 1 and r["tables"][0]["rows"][0]["月份"] == "2024年1月"
