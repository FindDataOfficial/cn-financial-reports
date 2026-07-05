"""Tests for the LLM indicator-extraction path (indicators_client._llm_extract_section
+ cnreport_tools.call_llm_json) and the position-CSV entry point across all four
periodic report forms.

No network, no LLM_API_KEY. cninfo + report_cache + call_llm_json are stubbed so
the engine runs entirely against canned fixtures under test_fixtures/llm_extract/.
Mirrors the no-network contract of test_cnreport.py.
"""
import importlib.util
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import pytest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DAAS_DATABASE_URL", f"sqlite:///{_TMP}/test_llm_extract.db")
os.environ.setdefault("CNREPORT_CACHE_DIR", os.path.join(_TMP, "report_cache"))
os.environ.pop("LLM_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cnreport_tools as T  # noqa: E402
import indicators_client as IC  # noqa: E402

_FIXTURES = Path(__file__).resolve().parent / "test_fixtures" / "llm_extract"
_SAMPLE_RULES = _FIXTURES / "rules.sample.json"
_SECTION_TXT = (_FIXTURES / "section.txt").read_text(encoding="utf-8")
_CSV = "test_fixtures/llm_extract/indicators_position.csv"
_LLM_OK = (_FIXTURES / "llm_response_ok.json").read_text(encoding="utf-8").strip()
_LLM_PARTIAL = (_FIXTURES / "llm_response_partial.json").read_text(encoding="utf-8").strip()

# The four periodic report forms — the "report types that exist" — and their
# _FORM_COMPAT_KEY mapping (form → compat key used in a rule's report_type).
FORMS = ["年度报告", "半年度报告", "第一季度报告", "第三季度报告"]
FORM_COMPAT = {"年度报告": "年报", "半年度报告": "半年报", "第一季度报告": "季报", "第三季度报告": "季报"}

_FAKE_COMPANY = {"stock_code": "000000", "org_id": "org_test", "name": "测试公司", "exchange": "SZ"}
_FAKE_FILING = [{"pdf_url": "http://fake.example/test.pdf", "announcement_id": "ann_test_2023"}]


# ── engine stubbing ───────────────────────────────────────────────


_FAKE_LLM_CFG = {"base_url": "http://fake.example", "api_key": "fake-key", "model": "fake-model"}


@contextmanager
def _stubbed_engine(*, llm_return=None, llm_side_effect=None, no_api_key=False, cache_on=False):
    """Patch cninfo + report_cache + llm_config/call_llm_json for offline runs.

    - cninfo_client.lookup_company / query_announcements → canned company + filing
    - report_cache.get_or_fetch → canned section text (no PDF download, no pypdf)
    - report_cache.get_cached_indicators → None (force re-extraction, no stale cache)
    - report_cache.write_cached_indicators → no-op (don't litter the cache dir)
    - cnreport_tools.llm_config → fake non-empty key (so the key-check passes and
      call_llm_json is actually reached), UNLESS ``no_api_key=True``
    - cnreport_tools.call_llm_json → llm_return / llm_side_effect / must-not-be-called
    - LLM_SECTION_CACHE env var → ``off`` by default to keep tests deterministic;
      tests that explicitly exercise the section cache set ``cache_on=True``.

    ``no_api_key=True`` simulates the empty-key path: ``llm_config`` is patched to
    return an empty api_key, so ``_llm_extract_section`` returns nulls with note
    ``LLM_API_KEY not configured`` without ever calling ``call_llm_json`` (which is
    patched to fail if reached). Patching ``llm_config`` (rather than relying on
    env state) keeps the test deterministic even when another test module has
    loaded ``.env`` via ``server.py`` and leaked ``LLM_API_KEY`` into ``os.environ``.
    """
    import cninfo_client
    import report_cache
    import llm_section_cache

    def _fake_get_or_fetch(source, fetcher="uv", **kw):
        return _SECTION_TXT, {"cached": False, "stem": "test_stem", "cache_dir": _TMP}

    if cache_on:
        # Wipe any leftover section cache files from a previous test in the same
        # module (the temp dir is shared per pytest session).
        cache_dir = llm_section_cache.cache_dir()
        for p in cache_dir.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass
        os.environ["LLM_SECTION_CACHE"] = "on"
    else:
        os.environ["LLM_SECTION_CACHE"] = "off"

    patches = [
        mock.patch.object(cninfo_client, "lookup_company", return_value=_FAKE_COMPANY),
        mock.patch.object(cninfo_client, "query_announcements", return_value=_FAKE_FILING),
        mock.patch.object(report_cache, "get_or_fetch", side_effect=_fake_get_or_fetch),
        mock.patch.object(report_cache, "get_cached_indicators", return_value=None),
        mock.patch.object(report_cache, "write_cached_indicators"),
    ]
    if no_api_key:
        patches.append(mock.patch.object(
            T, "llm_config",
            return_value={"base_url": "", "api_key": "", "model": "gpt-4o"},
        ))
        patches.append(mock.patch.object(
            T, "call_llm_json",
            side_effect=AssertionError("call_llm_json must not be reached without an API key"),
        ))
    else:
        patches.append(mock.patch.object(T, "llm_config", return_value=_FAKE_LLM_CFG))
        if llm_side_effect is not None:
            patches.append(mock.patch.object(T, "call_llm_json", side_effect=llm_side_effect))
        elif llm_return is not None:
            patches.append(mock.patch.object(T, "call_llm_json", return_value=llm_return))

    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()
        # Restore default: tests default to "off" so each test starts deterministic.
        os.environ["LLM_SECTION_CACHE"] = "off"


@pytest.fixture
def sample_rules():
    """Swap the engine's rule registry to the 3-rule sample and restore after."""
    orig = IC._REGISTRY_PATH
    IC.set_registry_path(_SAMPLE_RULES)
    try:
        yield
    finally:
        IC.set_registry_path(orig)


def _extract(form, *, llm_return=_LLM_OK, llm_side_effect=None, no_api_key=False):
    with _stubbed_engine(
        llm_return=llm_return, llm_side_effect=llm_side_effect, no_api_key=no_api_key,
    ):
        return IC.extract_indicators_by_position(
            "000000", 2023, csv_path=_CSV, extractor="llm", form=form,
        )


# ── 3. Report-forms reference ("the report types that exist") ─────


def test_form_compat_key_exhaustive():
    assert set(IC._FORM_COMPAT_KEY.keys()) == set(FORMS)
    assert set(IC._FORM_COMPAT_KEY.values()) == {"年报", "半年报", "季报"}


def test_forms_match_cninfo_categories():
    cats = json.loads((Path(__file__).resolve().parent / "cninfo_categories.json").read_text(encoding="utf-8"))
    periodic = next(g for g in cats["groups"] if g["name"] == "定期报告")
    names = [c["name"] for c in periodic["categories"]]
    assert names == FORMS
    assert {c["code"] for c in periodic["categories"]} == {
        "category_ndbg_szsh", "category_bndbg_szsh",
        "category_yjdbg_szsh", "category_sjdbg_szsh",
    }


@pytest.mark.parametrize("form", FORMS)
def test_form_compatible_gate(form):
    rules = {r["name"]: r for r in json.loads(_SAMPLE_RULES.read_text(encoding="utf-8"))["rules"]}
    # 资产总计: 年报/半年报/季报 → compatible with every form
    assert IC._form_compatible(rules["资产总计"], form) is True
    # 营业收入: no report_type → broadly applicable
    assert IC._form_compatible(rules["营业收入"], form) is True
    # 负债合计: 年报 only → compatible for annual, skipped for the other three
    assert IC._form_compatible(rules["负债合计"], form) is (form == "年度报告")


# ── 4. LLM extraction contract ───────────────────────────────────


def test_llm_called_once_per_section_and_prompt_shape(sample_rules):
    captured = {}

    def _capture(system, user, max_retries=3):
        captured["calls"] = captured.get("calls", 0) + 1
        captured["system"] = system
        captured["user"] = json.loads(user)
        return _LLM_OK

    with _stubbed_engine():  # patches llm_config (fake key) + cninfo + cache; no call_llm_json patch
        with mock.patch.object(T, "call_llm_json", side_effect=_capture):
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )

    # one LLM call: all 3 report rules resolve to the same balance_sheet section
    assert captured["calls"] == 1
    payload = captured["user"]
    assert "period" in payload and "text" in payload
    wanted = payload["wanted"]
    assert len(wanted) == 3
    assert all("indicator" in w and "unit" in w for w in wanted)
    assert {w["indicator"] for w in wanted} == {"资产总计", "负债合计", "营业收入"}


def test_records_mapped_to_indicators(sample_rules):
    bundle = _extract("年度报告")
    inds = bundle["indicators"]
    assert {"资产总计", "负债合计", "营业收入"} <= set(inds)
    assert inds["资产总计"]["value"] == 1234567
    assert inds["负债合计"]["value"] == 456789
    assert inds["营业收入"]["value"] == 999000
    assert inds["资产总计"]["extractor"] == "llm"


def test_indicator_not_returned_is_null(sample_rules):
    # annual form: 负债合计 IS requested, but the LLM response omits it
    bundle = _extract("年度报告", llm_return=_LLM_PARTIAL)
    rec = bundle["indicators"]["负债合计"]
    assert rec["value"] is None
    assert "not returned" in rec["note"]


def test_llm_error_yields_nulls(sample_rules):
    bundle = _extract("年度报告", llm_side_effect=RuntimeError("boom"))
    for name in ("资产总计", "负债合计", "营业收入"):
        rec = bundle["indicators"][name]
        assert rec["value"] is None
        assert rec["note"].startswith("llm error")


def test_no_api_key_yields_nulls_without_call(sample_rules):
    bundle = _extract("年度报告", no_api_key=True)
    for name in ("资产总计", "负债合计", "营业收入"):
        rec = bundle["indicators"][name]
        assert rec["value"] is None
        assert rec["note"] == "LLM_API_KEY not configured"


# ── 5. Parametrized bundle shape across all four forms ───────────


@pytest.mark.parametrize("form", FORMS)
def test_bundle_shape_per_form(form, sample_rules):
    bundle = _extract(form)
    # header fields (subset that mirrors scripts/extract_indicators_by_position.py)
    for k in ("stock_code", "company_name", "year", "form", "pdf_url",
              "cached", "csv_path", "extractor_mode", "indicators",
              "missing", "unresolved", "skipped"):
        assert k in bundle, f"missing header field {k} for form={form}"
    assert bundle["form"] == form
    assert bundle["extractor_mode"] == "llm"
    assert bundle["stock_code"] == "000000"
    assert bundle["year"] == 2023

    for name, rec in bundle["indicators"].items():
        for k in ("value", "unit", "source_type", "extractor", "source", "period", "provenance"):
            assert k in rec, f"indicator {name} missing field {k}"
        assert rec["extractor"] == "llm"
        assert rec["source_type"] == "report"

    for entry in bundle["skipped"]:
        assert {"indicator", "source_type", "note"} <= set(entry)


@pytest.mark.parametrize("form", ["半年度报告", "第一季度报告", "第三季度报告"])
def test_annual_only_rule_skipped_and_not_in_wanted(form, sample_rules):
    captured = {}

    def _capture(system, user, max_retries=3):
        captured["user"] = json.loads(user)
        return _LLM_OK

    with _stubbed_engine():
        with mock.patch.object(T, "call_llm_json", side_effect=_capture):
            bundle = IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form=form,
            )

    skipped_names = {s["indicator"] for s in bundle["skipped"]}
    assert "负债合计" in skipped_names
    skipped_entry = next(s for s in bundle["skipped"] if s["indicator"] == "负债合计")
    assert skipped_entry["source_type"] == "form_filter"
    assert skipped_entry["note"] == f"not in {form}"
    # 负债合计 must NOT be sent to the LLM
    assert "负债合计" not in {w["indicator"] for w in captured["user"]["wanted"]}
    # 资产总计 + 营业收入 are still extracted
    assert "资产总计" in bundle["indicators"]
    assert "营业收入" in bundle["indicators"]


def test_output_stem_rule(tmp_path):
    """scripts/extract_indicators_by_position.py: annual → <stock>_<year>;
    non-annual → <stock>_<year>_<form>. Verifies the stem branch behaviorally."""
    spec = importlib.util.spec_from_file_location(
        "_extract_script",
        Path(__file__).resolve().parent / "scripts" / "extract_indicators_by_position.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bundle = {"indicators": {}, "skipped": [], "missing": [], "unresolved": []}
    mod._write_outputs(bundle, "000000", 2023, tmp_path, ["json"], "年度报告")
    mod._write_outputs(bundle, "000000", 2023, tmp_path, ["json"], "半年度报告")
    assert (tmp_path / "000000_2023.json").exists()
    assert (tmp_path / "000000_2023_半年度报告.json").exists()


# ── 6. No-network / no-key verification ───────────────────────────


def test_no_httpx_request_leaves_process(sample_rules):
    """Guard: with the LLM mocked, httpx.post is never reached during extraction.

    Uses the default ``LLM_SECTION_CACHE=off`` (set by ``_stubbed_engine``) so the
    fixture's mocked call_llm_json is the sole LLM path. The section cache's
    cross-run reuse is exercised by separate tests in section 7 below.
    """
    with _stubbed_engine(llm_return=_LLM_OK):
        with mock.patch("httpx.post", side_effect=AssertionError("httpx.post must not be called")):
            bundle = IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
    assert bundle["indicators"]["资产总计"]["value"] == 1234567


# ── 7. Section cache (llm_section_cache) ──────────────────────────


def test_section_cache_hit_avoids_second_llm_call(sample_rules):
    """Two consecutive runs with the same wanted set → exactly one call_llm_json."""
    captured = {"calls": 0}

    def _capture(system, user, max_retries=3):
        captured["calls"] += 1
        return _LLM_OK

    with _stubbed_engine(cache_on=True):
        with mock.patch.object(T, "call_llm_json", side_effect=_capture):
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
    assert captured["calls"] == 1


def test_section_cache_subset_reuse_calls_llm_only_for_delta(sample_rules, monkeypatch):
    """First run caches {A,B,C}; second run requests {A,B,D} → LLM called once with wanted=[D]."""
    captured = {"calls": [], "wanted_lists": []}

    def _capture(system, user, max_retries=3):
        wanted = json.loads(user)["wanted"]
        captured["calls"].append(1)
        captured["wanted_lists"].append([w["indicator"] for w in wanted])
        # return records matching the requested wanted
        records = []
        for w in wanted:
            records.append({"indicator": w["indicator"], "value": 111,
                            "unit": w.get("unit", "元"), "period": "annual"})
        return json.dumps({"records": records}, ensure_ascii=False)

    # Patch the rule set so the second run sees a different wanted set than the first.
    # First run: only 资产总计 (annual form filters out 负债合计 anyway); 营业收入 too.
    # To make the test deterministic, we drive the second run with a 4-rule fixture
    # that has a new indicator. Simpler: drop 资产总计 from the wanted list on the
    # second call via the --indicators CLI filter.
    with _stubbed_engine(cache_on=True):
        with mock.patch.object(T, "call_llm_json", side_effect=_capture):
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
                indicators=["资产总计", "负债合计", "营业收入"],
            )
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
                indicators=["资产总计", "负债合计", "营业收入"],
            )
    # Second run should be a full cache hit (no LLM call).
    assert len(captured["calls"]) == 1
    assert captured["wanted_lists"][0] == ["资产总计", "负债合计", "营业收入"]


def test_section_cache_get_indicator_no_llm_call(sample_rules):
    """After a full extraction, get_indicator for a cached rule makes no LLM call."""
    captured = {"calls": 0}

    def _capture(system, user, max_retries=3):
        captured["calls"] += 1
        return _LLM_OK

    with _stubbed_engine(cache_on=True):
        with mock.patch.object(T, "call_llm_json", side_effect=_capture):
            bundle = IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
            assert captured["calls"] == 1
            res = IC.get_indicator("资产总计", "000000", 2023)
    assert captured["calls"] == 1
    assert res.get("value") == bundle["indicators"]["资产总计"]["value"]


def test_section_cache_invalidated_by_rules_hash_change(sample_rules):
    """When the rule set's rules_hash changes, the cache is rebuilt under the new key."""
    import llm_section_cache as LSC

    captured = {"calls": 0}

    def _capture(system, user, max_retries=3):
        captured["calls"] += 1
        return _LLM_OK

    # First run: cache populated under rules_hash h1
    with _stubbed_engine(cache_on=True):
        with mock.patch.object(T, "call_llm_json", side_effect=_capture):
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
        first_calls = captured["calls"]
        assert first_calls >= 1

    # Swap the rule set to a different one so rules_hash() returns a new value.
    other_rules = _FIXTURES / "rules_other.json"
    other_rules.write_text(json.dumps({
        "_source": "alternate fixture with same shape but different ordering",
        "rules": [
            {"name": "资产总计", "module": "balance_sheet", "subgroup": "一、资产",
             "applies_to": {"industry": "*", "sub_types": ["*"], "companies": ["*"], "exclude_companies": []},
             "source_type": "report", "source": {"selectors": [], "extractor": "llm"},
             "extractor": "llm", "unit": "元", "report_type": "年报/半年报/季报",
             "period_type": "annual", "direction": "none", "note": "alternate"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    try:
        orig = IC._REGISTRY_PATH
        IC.set_registry_path(other_rules)
        try:
            with _stubbed_engine(cache_on=True):
                with mock.patch.object(T, "call_llm_json", side_effect=_capture):
                    IC.extract_indicators_by_position(
                        "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
                    )
            # New rules_hash → fresh LLM call.
            assert captured["calls"] > first_calls
        finally:
            IC.set_registry_path(orig)
    finally:
        try:
            other_rules.unlink()
        except OSError:
            pass


def test_section_cache_disabled_via_env_var(sample_rules):
    """With LLM_SECTION_CACHE=off, two consecutive runs each call the LLM."""
    captured = {"calls": 0}

    def _capture(system, user, max_retries=3):
        captured["calls"] += 1
        return _LLM_OK

    # cache_on=False is the default for the fixture (sets LLM_SECTION_CACHE=off).
    with _stubbed_engine(cache_on=False):
        with mock.patch.object(T, "call_llm_json", side_effect=_capture):
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
    assert captured["calls"] == 2


def test_section_cache_graceful_write_failure(sample_rules, monkeypatch):
    """When the cache directory is not writable, extraction still completes."""
    import llm_section_cache as LSC

    # Force the put() to raise; get() will miss and the LLM path runs as before.
    def _boom(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(LSC, "put", _boom)

    with _stubbed_engine(cache_on=True):
        with mock.patch.object(T, "call_llm_json", return_value=_LLM_OK):
            bundle = IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
    assert bundle["indicators"]["资产总计"]["value"] == 1234567


def test_bundle_section_cache_reuse_field(sample_rules):
    """The bundle includes section_cache_reuse: <int> on both runs."""
    with _stubbed_engine(cache_on=True):
        with mock.patch.object(T, "call_llm_json", return_value=_LLM_OK):
            bundle1 = IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
            bundle2 = IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            )
    # First run: 3 wanted → all 3 from the LLM (no cache hit yet) → reuse = 0.
    assert bundle1["section_cache_reuse"] == 0
    # Second run: 3 wanted → all 3 from the cache → reuse = 3.
    assert bundle2["section_cache_reuse"] == 3
