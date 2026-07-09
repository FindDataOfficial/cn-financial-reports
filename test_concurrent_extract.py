"""Tests for concurrent extraction: ``indicators_client._map_merge``,
``extract_indicators(concurrency=...)``, and ``extract_indicators_batch``.

No network, no ``LLM_API_KEY``. Reuses the offline engine stub + fixtures from
``test_llm_indicator_extract.py`` (cninfo + report_cache + call_llm_json stubbed
so the engine runs entirely against canned fixtures). Mirrors the no-network
contract of ``test_cnreport.py``.
"""
import sys
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reuse the offline engine stub + fixtures from the LLM-extract test module.
from test_llm_indicator_extract import (  # noqa: E402
    _stubbed_engine, _SAMPLE_RULES, _CSV, _LLM_OK, _FAKE_COMPANY,
)

import cnreport_tools as T  # noqa: E402
import indicators_client as IC  # noqa: E402


@pytest.fixture
def sample_rules():
    """Swap the engine's rule registry to the 3-rule sample and restore after."""
    orig = IC._REGISTRY_PATH
    IC.set_registry_path(_SAMPLE_RULES)
    try:
        yield
    finally:
        IC.set_registry_path(orig)


def _overlap_tracker(delay: float = 0.05):
    """Return ``(fn, state)`` where ``fn`` sleeps and ``state`` tracks max in-flight.

    Uses its own lock (not the Mock's call tracking) so assertions are race-free
    even though ``unittest.mock`` is not fully thread-safe internally.
    """
    state = {"inflight": 0, "max": 0, "lock": threading.Lock()}

    def fn(i):
        with state["lock"]:
            state["inflight"] += 1
            state["max"] = max(state["max"], state["inflight"])
        time.sleep(delay)
        with state["lock"]:
            state["inflight"] -= 1
        return i

    return fn, state


def _llm_overlap_tracker(delay: float = 0.05):
    """Like ``_overlap_tracker`` but for a ``call_llm_json`` mock (ignores args)."""
    state = {"inflight": 0, "max": 0, "lock": threading.Lock()}

    def fn(system, user, max_retries=3):
        with state["lock"]:
            state["inflight"] += 1
            state["max"] = max(state["max"], state["inflight"])
        time.sleep(delay)
        with state["lock"]:
            state["inflight"] -= 1
        return _LLM_OK

    return fn, state


# ── _map_merge unit tests ─────────────────────────────────────────


def test_map_merge_preserves_input_order():
    out = IC._map_merge(list(range(8)), lambda i: i * 10, 4)
    assert out == [i * 10 for i in range(8)]


def test_map_merge_overlaps_concurrently():
    fn, state = _overlap_tracker()
    out = IC._map_merge(list(range(5)), fn, 4)
    assert out == list(range(5))
    assert state["max"] >= 2  # genuine concurrency, not serial


def test_map_merge_respects_cap():
    fn, state = _overlap_tracker()
    IC._map_merge(list(range(6)), fn, 2)
    assert state["max"] <= 2


def test_map_merge_concurrency_one_is_sequential():
    fn, state = _overlap_tracker()
    IC._map_merge(list(range(5)), fn, 1)
    assert state["max"] == 1  # no overlap


def test_map_merge_inline_when_single_item():
    # len(items) <= 1 → no pool; still returns the correct result.
    assert IC._map_merge([42], lambda i: i + 1, 8) == [43]
    assert IC._map_merge([], lambda i: i, 8) == []


# ── extract_indicators concurrency (integration) ───────────────────


def _extract(*, concurrency=None, llm_return=_LLM_OK, cache_on=False):
    with _stubbed_engine(llm_return=llm_return, cache_on=cache_on):
        return IC.extract_indicators_by_position(
            "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
            concurrency=concurrency,
        )


def test_concurrent_run_equals_sequential(sample_rules):
    """A concurrency>1 run produces results equal to concurrency=1."""
    seq = _extract(concurrency=1)
    par = _extract(concurrency=4)
    for key in ("indicators", "missing", "unresolved", "skipped"):
        assert seq[key] == par[key], f"{key} differs between sequential and concurrent"


def test_env_var_sets_concurrency(sample_rules, monkeypatch):
    monkeypatch.setenv("EXTRACT_CONCURRENCY", "3")
    with _stubbed_engine():
        bundle = IC.extract_indicators_by_position(
            "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
        )
    assert bundle["concurrency"] == 3


def test_bundle_carries_concurrency_field(sample_rules):
    assert _extract(concurrency=4)["concurrency"] == 4
    assert _extract(concurrency=1)["concurrency"] == 1


def test_call_count_unchanged_by_concurrency(sample_rules):
    """concurrency changes *when* calls issue, not how many."""
    counts = {}
    for cap in (1, 4):
        captured = {"n": 0}

        def _count(system, user, max_retries=3):
            captured["n"] += 1
            return _LLM_OK

        with _stubbed_engine():
            with mock.patch.object(T, "call_llm_json", side_effect=_count):
                IC.extract_indicators_by_position(
                    "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
                    concurrency=cap,
                )
        counts[cap] = captured["n"]
    assert counts[1] == counts[4]


def test_section_cache_composes_with_concurrency(sample_rules):
    """A concurrent run populates the cache; a second run makes 0 LLM calls."""
    captured = {"n": 0}

    def _count(system, user, max_retries=3):
        captured["n"] += 1
        return _LLM_OK

    with _stubbed_engine(cache_on=True):
        with mock.patch.object(T, "call_llm_json", side_effect=_count):
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
                concurrency=4,
            )
            IC.extract_indicators_by_position(
                "000000", 2023, csv_path=_CSV, extractor="llm", form="年度报告",
                concurrency=4,
            )
    assert captured["n"] == 1  # second run fully served from the section cache


# ── extract_indicators_batch ───────────────────────────────────────


def test_batch_empty_targets():
    out = IC.extract_indicators_batch([])
    assert out["results"] == {}
    assert out["failures"] == []
    assert out["concurrency"] >= 1


def test_batch_runs_targets_concurrently(sample_rules):
    """3 targets at concurrency=3 → call_llm_json calls overlap in time."""
    fn, state = _llm_overlap_tracker()
    targets = [("000001", 2023), ("000002", 2023), ("000003", 2023)]
    with _stubbed_engine():
        with mock.patch.object(T, "call_llm_json", side_effect=fn):
            out = IC.extract_indicators_batch(
                targets, concurrency=3, csv_path=_CSV, extractor_mode="llm",
            )
    assert len(out["results"]) == 3
    assert out["failures"] == []
    assert state["max"] >= 2  # genuine cross-target concurrency


def test_batch_isolates_failing_target(sample_rules):
    """A target whose lookup raises is recorded in failures; the others succeed."""
    import cninfo_client

    def _lookup(t):
        if t == "BAD":
            raise ValueError("boom")
        return _FAKE_COMPANY

    targets = [("000001", 2023), ("BAD", 2023), ("000003", 2023)]
    with _stubbed_engine():
        with mock.patch.object(cninfo_client, "lookup_company", side_effect=_lookup):
            out = IC.extract_indicators_batch(
                targets, concurrency=3, csv_path=_CSV, extractor_mode="llm",
            )
    assert {"000001_2023", "000003_2023"} <= set(out["results"])
    assert "BAD_2023" not in out["results"]
    fail_targets = {f["target"] for f in out["failures"]}
    assert "BAD_2023" in fail_targets


def test_batch_result_is_order_independent(sample_rules):
    targets = [("000001", 2023), ("000002", 2023), ("000003", 2023)]
    with _stubbed_engine():
        out1 = IC.extract_indicators_batch(
            targets, concurrency=3, csv_path=_CSV, extractor_mode="llm",
        )
        out2 = IC.extract_indicators_batch(
            targets, concurrency=3, csv_path=_CSV, extractor_mode="llm",
        )
    assert set(out1["results"]) == set(out2["results"])
    for k in out1["results"]:
        assert out1["results"][k]["indicators"] == out2["results"][k]["indicators"]


def test_batch_cap_defaults_and_respected(sample_rules, monkeypatch):
    """Default batch cap is 2; with 4 targets, at most 2 LLM calls in-flight."""
    monkeypatch.delenv("EXTRACT_BATCH_CONCURRENCY", raising=False)
    fn, state = _llm_overlap_tracker()
    targets = [(f"00000{i}", 2023) for i in range(1, 5)]  # 4 targets
    with _stubbed_engine():
        with mock.patch.object(T, "call_llm_json", side_effect=fn):
            out = IC.extract_indicators_batch(
                targets, csv_path=_CSV, extractor_mode="llm",  # concurrency=None → default
            )
    assert len(out["results"]) == 4
    assert out["concurrency"] == 2
    assert state["max"] <= 2  # cap respected


def test_batch_concurrency_one_is_sequential(sample_rules):
    fn, state = _llm_overlap_tracker()
    targets = [("000001", 2023), ("000002", 2023), ("000003", 2023)]
    with _stubbed_engine():
        with mock.patch.object(T, "call_llm_json", side_effect=fn):
            IC.extract_indicators_batch(
                targets, concurrency=1, csv_path=_CSV, extractor_mode="llm",
            )
    assert state["max"] == 1  # strictly sequential


def test_no_httpx_request_leaves_process(sample_rules):
    """With the LLM mocked, httpx.post is never reached during concurrent extraction."""
    with _stubbed_engine(llm_return=_LLM_OK):
        with mock.patch("httpx.post", side_effect=AssertionError("httpx.post must not be called")):
            out = IC.extract_indicators_batch(
                [("000001", 2023), ("000002", 2023)], concurrency=2,
                csv_path=_CSV, extractor_mode="llm",
            )
    assert len(out["results"]) == 2
