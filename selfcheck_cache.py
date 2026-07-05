"""Self-check for the report cache + three-statements extraction — no network.

Run:  cd mcp/cnreport-mcp && uv run python selfcheck_cache.py

Covers:
  1. report_cache.cache_key: provenance / url-hash / local-path (None).
  2. report_cache.get_or_fetch: miss → fetch+store, hit → no re-fetch,
     local-path pass-through.
  3. report_cache.list_cache / clear_cache (by company / company+year / all).
  4. cnreport_tools.resolve_statement: consolidated / un-prefixed fallback /
     missing.
  5. cnreport_tools.get_financial_statements end-to-end (CNINFO + fetch
     stubbed), incl. the cache-hit path and the company-not-found error.

Uses a temp CNREPORT_CACHE_DIR. No live network / DB.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp()
os.environ["CNREPORT_CACHE_DIR"] = _TMP
os.environ["DAAS_DATABASE_URL"] = f"sqlite:///{_TMP}/selfcheck_cache.db"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_MODELS = Path(__file__).resolve().parent.parent / "models"
if str(_MODELS) not in sys.path:
    sys.path.insert(0, str(_MODELS))

import cnreport_tools as T  # noqa: E402
import report_cache as RC  # noqa: E402


def check_cache_key():
    # provenance key
    k = RC.cache_key(
        "http://x/a.pdf",
        stock_code="600519", year=2023, form="年度报告", announcement_id="1219730876",
    )
    assert k == "600519_2023_年度报告_1219730876", k
    # url-hash fallback (no announcement_id)
    k2 = RC.cache_key("http://x/a.pdf")
    assert k2.startswith("url_") and len(k2) == 4 + 16, k2
    # same url → same key
    assert RC.cache_key("http://x/a.pdf") == k2
    # local path → None (never cached)
    assert RC.cache_key("/tmp/foo.pdf") is None
    assert RC.cache_key("relative.pdf") is None
    print("  ✓ cache_key: provenance / url-hash / local-path(None)")


def check_get_or_fetch():
    calls = {"n": 0}
    fake_text = "第一节 概述\n公司简介。\n第二节 财务\n数据。"

    def fake(source, fetcher="uv"):
        calls["n"] += 1
        return fake_text, b"%PDF-1.4 fake bytes"

    _orig = T.fetch_source_with_bytes
    T.fetch_source_with_bytes = fake
    try:
        # miss
        text, info = RC.get_or_fetch(
            "http://x/report.pdf",
            stock_code="600519", year=2023, form="年度报告", announcement_id="A1",
        )
        assert text == fake_text, text
        assert info["cached"] is False, info
        assert calls["n"] == 1, calls
        d = Path(info["cache_dir"])
        stem = info["stem"]
        assert (d / f"{stem}.txt").exists()
        assert (d / f"{stem}.pdf").exists()
        assert (d / f"{stem}.outline.json").exists()

        # hit — no re-fetch
        text2, info2 = RC.get_or_fetch(
            "http://x/report.pdf",
            stock_code="600519", year=2023, form="年度报告", announcement_id="A1",
        )
        assert text2 == fake_text
        assert info2["cached"] is True, info2
        assert calls["n"] == 1, f"expected 1 fetch call, got {calls['n']}"

        # local path → not cached, fetch_source still called
        text3, info3 = RC.get_or_fetch("/tmp/does-not-exist.pdf")
        assert info3["stem"] is None, info3
        assert info3["cached"] is False, info3
        assert calls["n"] == 2, calls
    finally:
        T.fetch_source_with_bytes = _orig
    print("  ✓ get_or_fetch: miss→store, hit→no re-fetch, local-path pass-through")


def check_list_clear():
    RC.clear_cache()
    calls = {"n": 0}

    def fake(source, fetcher="uv"):
        calls["n"] += 1
        return f"text {calls['n']}", b"pdf bytes"

    _orig = T.fetch_source_with_bytes
    T.fetch_source_with_bytes = fake
    try:
        RC.get_or_fetch(
            "http://x/a.pdf", stock_code="600519", year=2023,
            form="年度报告", announcement_id="A1",
        )
        RC.get_or_fetch(
            "http://x/b.pdf", stock_code="600519", year=2022,
            form="年度报告", announcement_id="A2",
        )
        RC.get_or_fetch(
            "http://x/c.pdf", stock_code="000001", year=2023,
            form="年度报告", announcement_id="A3",
        )
        listed = RC.list_cache()
        assert listed["count"] == 3, listed
        # entries carry parsed provenance
        stocks = {e.get("stock_code") for e in listed["entries"]}
        assert stocks == {"600519", "000001"}, stocks

        # clear by company
        r = RC.clear_cache(stock_code="600519")
        assert r["removed"] == 2, r
        assert RC.list_cache()["count"] == 1

        # re-add one 600519/2023, then clear by company+year
        RC.get_or_fetch(
            "http://x/a.pdf", stock_code="600519", year=2023,
            form="年度报告", announcement_id="A1",
        )
        r = RC.clear_cache(stock_code="600519", year=2023)
        assert r["removed"] == 1, r

        # clear all
        r = RC.clear_cache()
        assert r["removed"] >= 1, r
        assert RC.list_cache()["count"] == 0
    finally:
        T.fetch_source_with_bytes = _orig
    print("  ✓ list_cache / clear_cache: by company / by company+year / all")


def check_resolve_statement():
    # consolidated all three
    outline_consolidated = [
        {"level": 1, "title": "第十节 财务报告", "ordinal": 10},
        {"level": 2, "title": "1、 合并资产负债表", "ordinal": 11},
        {"level": 2, "title": "2、 合并利润表", "ordinal": 12},
        {"level": 2, "title": "3、 合并现金流量表", "ordinal": 13},
    ]
    assert T.resolve_statement(outline_consolidated, "balance_sheet")["title"] == "1、 合并资产负债表"
    assert T.resolve_statement(outline_consolidated, "income_statement")["title"] == "2、 合并利润表"
    assert T.resolve_statement(outline_consolidated, "cashflow")["title"] == "3、 合并现金流量表"

    # un-prefixed fallback (no 合并)
    outline_plain = [
        {"level": 2, "title": "1、 利润表", "ordinal": 1},
        {"level": 2, "title": "2、 资产负债表", "ordinal": 2},
        {"level": 2, "title": "3、 现金流量表", "ordinal": 3},
    ]
    assert T.resolve_statement(outline_plain, "income_statement")["title"] == "1、 利润表"
    assert T.resolve_statement(outline_plain, "balance_sheet")["title"] == "2、 资产负债表"
    assert T.resolve_statement(outline_plain, "cashflow")["title"] == "3、 现金流量表"

    # missing one → None, others still resolve
    outline_missing = [
        {"level": 2, "title": "1、 合并资产负债表", "ordinal": 1},
        {"level": 2, "title": "2、 合并利润表", "ordinal": 2},
        # cashflow absent
    ]
    assert T.resolve_statement(outline_missing, "cashflow") is None
    assert T.resolve_statement(outline_missing, "income_statement")["title"] == "2、 合并利润表"
    print("  ✓ resolve_statement: consolidated / un-prefixed fallback / missing")


def check_get_financial_statements():
    """End-to-end with CNINFO + fetch stubbed."""
    import cninfo_client

    _orig_post = cninfo_client._post_json
    fixtures = Path(__file__).resolve().parent / "test_fixtures"
    topsearch = json.loads((fixtures / "cninfo_topsearch.json").read_text(encoding="utf-8"))
    hisann = json.loads((fixtures / "cninfo_hisannouncement.json").read_text(encoding="utf-8"))

    def fake_post(path, data):
        if "topSearch" in path:
            return topsearch
        if "hisAnnouncement" in path:
            return hisann
        raise AssertionError(f"unexpected path: {path}")

    cninfo_client._post_json = fake_post

    report_text = (
        "第十节 财务报告 ......... 100\n"
        "1、 合并资产负债表 ......... 101\n"
        "2、 合并利润表 ......... 105\n"
        "3、 合并现金流量表 ......... 110\n"
        "正文\n第十节 财务报告\n本节为财务报告。\n"
        "1、 合并资产负债表\n资产总计 100亿。\n"
        "2、 合并利润表\n营业收入 200亿。\n"
        "3、 合并现金流量表\n经营现金流 50亿。\n"
    )
    _orig_fetch = T.fetch_source_with_bytes
    T.fetch_source_with_bytes = lambda *_a, **_kw: (report_text, b"%PDF fake")
    try:
        RC.clear_cache()  # ensure first call is a miss
        r = T.get_financial_statements("600519", year=2023)
        assert "error" not in r, r
        assert r["stock_code"] == "600519", r
        assert r["missing"] == [], r
        assert set(r["statements"].keys()) == {"income_statement", "balance_sheet", "cashflow"}, r
        assert "营业收入 200亿" in r["statements"]["income_statement"]["text"], \
            r["statements"]["income_statement"]["text"]
        assert "资产总计 100亿" in r["statements"]["balance_sheet"]["text"]
        assert "经营现金流 50亿" in r["statements"]["cashflow"]["text"]
        assert r["cached"] is False, r  # first call = miss

        # second call → cache hit, no re-fetch
        _calls = {"n": 0}

        def fake2(*_a, **_kw):
            _calls["n"] += 1
            return report_text, b"%PDF fake"

        T.fetch_source_with_bytes = fake2
        r2 = T.get_financial_statements("600519", year=2023)
        assert r2["cached"] is True, r2
        assert _calls["n"] == 0, _calls  # no fetch on cache hit

        # company not found → error, no network
        cninfo_client._post_json = lambda path, data: (
            [] if "topSearch" in path else {"announcements": []}
        )
        r3 = T.get_financial_statements("NOPE", year=2023)
        assert "error" in r3, r3
        print("  ✓ get_financial_statements: 3 statements / cache hit / company-not-found")
    finally:
        cninfo_client._post_json = _orig_post
        T.fetch_source_with_bytes = _orig_fetch
    RC.clear_cache()


def main():
    print("cache-key checks:")
    check_cache_key()
    print("get_or_fetch checks:")
    check_get_or_fetch()
    print("list/clear checks:")
    check_list_clear()
    print("resolve_statement checks:")
    check_resolve_statement()
    print("get_financial_statements checks:")
    check_get_financial_statements()
    print("\nALL CACHE SELF-CHECKS PASSED")


if __name__ == "__main__":
    main()
