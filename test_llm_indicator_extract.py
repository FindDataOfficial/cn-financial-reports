#!/usr/bin/env python3
"""Tests for LLM indicator extraction with Pydantic output validation.

These tests exercise the full LLM extraction pipeline:
- _llm_extract_section (groups rules by module, calls call_llm_pydantic once per module)
- _resolve_rule_value (report rules flow)
- extract_indicators (end-to-end)

LLM calls are mocked at the call_llm_pydantic level.
"""

import copy
import json
import os
import pathlib
import re
import sys
import tempfile
from unittest.mock import ANY, MagicMock, call, patch

import pytest

# Isolate the rules database so set_registry_path(sample) (which now seeds the
# rules DB) never contaminates the real daas.db. Mirrors test_cnreport.py.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("DAAS_DATABASE_URL", f"sqlite:///{_TMP}/test_llm.db")

# ── helpers ────────────────────────────────────────────────────────────


def _module_to_model_class(module: str, reg: dict):
    """Mirrors indicators_models.model_for_module to build a model class
    from the sample rules, matching what the production code would create
    at import time."""
    from indicators_models import model_for_module

    return model_for_module(module)


def _fake_pydantic_instance(model_class, values: dict[str, object]):
    """Build a Pydantic model instance populated with *values*.

    Production code calls ``model_class.model_validate(raw)``, so tests
    must mock ``call_llm_pydantic`` to return a model instance whose
    ``model_dump()`` produces the expected dict.
    """
    inst = model_class.model_validate(values)
    return inst


# ── fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def sample_rules():
    """Load the 7-rule sample fixture."""
    return json.loads(
        (pathlib.Path(__file__).parent / "test_fixtures" / "indicator_rules.sample.json").read_text()
    )


@pytest.fixture
def sample_rules_path():
    return pathlib.Path(__file__).parent / "test_fixtures" / "indicator_rules.sample.json"


@pytest.fixture
def mock_text():
    """Short mock report body text for section extraction."""
    return (
        "一、 资产\n"
        "资产总计 100 200\n"
        "负债合计 50 60\n"
        "所有者权益合计 50 140\n"
        "一、 营业收入\n"
        "营业收入 100 120\n"
        "营业支出 70 80\n"
    )


@pytest.fixture
def mock_outline():
    return [
        {"ordinal": 1, "title": "一、 资产", "level": 1, "page": 1},
        {"ordinal": 2, "title": "一、 营业收入", "level": 1, "page": 1},
    ]


@pytest.fixture
def mock_company():
    return {"stock_code": "000001", "name": "平安银行", "org_id": "gssz0000001"}


# ── core tests ─────────────────────────────────────────────────────────


class TestLLMExtractSection:
    """Test _llm_extract_section groups rules by module and calls the LLM."""

    @patch("indicators_client.call_llm_pydantic")
    @patch("indicators_client.resolve_rule")
    def test_extracts_single_module(
        self, mock_resolve_rule, mock_call_llm,
        sample_rules_path, mock_text, mock_outline, mock_company,
    ):
        """Single module: one call_llm_pydantic call, correct model used."""
        from indicators_client import _llm_extract_section, set_registry_path
        from indicators_models import get_registry

        set_registry_path(sample_rules_path)
        reg = get_registry()

        # Use only balance_sheet rules
        rules = [
            r for r in json.loads(sample_rules_path.read_text())
            if r["module"] == "balance_sheet"
        ]
        # 3 rules: 资产总计, 负债合计, 所有者权益合计
        assert len(rules) == 3

        model_class = reg["balance_sheet"]

        def mock_resolve(rname):
            return next((r for r in rules if r["name"] == rname), None)

        mock_resolve_rule.side_effect = mock_resolve

        # Mock returns a valid instance with all three fields
        mock_call_llm.return_value = _fake_pydantic_instance(model_class, {
            "资产总计": 100.0,
            "负债合计": 50.0,
            "所有者权益合计": 50.0,
        })

        results = _llm_extract_section(
            rules, mock_text, mock_outline, mock_company, "auto", mock_text,
        )

        # One LLM call for one module
        assert mock_call_llm.call_count == 1
        # Check the correct model class was passed
        call_kwargs = mock_call_llm.call_args.kwargs
        assert call_kwargs["model_class"] is model_class

        # All three indicators should be extracted
        assert len(results) == 3
        assert results[0]["name"] == "资产总计"
        assert results[0]["value"] == 100.0
        assert results[1]["name"] == "负债合计"
        assert results[1]["value"] == 50.0
        assert results[2]["name"] == "所有者权益合计"
        assert results[2]["value"] == 50.0

    @patch("indicators_client.call_llm_pydantic")
    @patch("indicators_client.resolve_rule")
    def test_extracts_multiple_modules(
        self, mock_resolve_rule, mock_call_llm,
        sample_rules_path, mock_text, mock_outline, mock_company,
    ):
        """Two modules: two call_llm_pydantic calls, each with correct model."""
        from indicators_client import _llm_extract_section, set_registry_path
        from indicators_models import get_registry

        set_registry_path(sample_rules_path)
        reg = get_registry()

        all_rules = json.loads(sample_rules_path.read_text())
        assert len(all_rules) == 7  # 3 balance_sheet + 4 income_statement

        bs_model = reg["balance_sheet"]
        is_model = reg["income_statement"]

        def mock_resolve(rname):
            return next((r for r in all_rules if r["name"] == rname), None)

        mock_resolve_rule.side_effect = mock_resolve

        call_count = [0]

        def mock_llm_side_effect(system, user, model_class, **kwargs):
            call_count[0] += 1
            if model_class is bs_model:
                return _fake_pydantic_instance(bs_model, {
                    "资产总计": 100.0,
                    "负债合计": 50.0,
                    "所有者权益合计": 50.0,
                })
            elif model_class is is_model:
                return _fake_pydantic_instance(is_model, {
                    "营业收入": 100.0,
                    "营业支出": 70.0,
                    "营业利润": 30.0,
                    "净利润": 30.0,
                })
            return None

        mock_call_llm.side_effect = mock_llm_side_effect

        results = _llm_extract_section(
            all_rules, mock_text, mock_outline, mock_company, "auto", mock_text,
        )

        assert mock_call_llm.call_count == 2
        assert len(results) == 7

        # Verify both modules' calls used correct model classes
        called_models = {c.kwargs["model_class"] for c in mock_call_llm.call_args_list}
        assert bs_model in called_models
        assert is_model in called_models

    @patch("indicators_client.call_llm_pydantic")
    @patch("indicators_client.resolve_rule")
    def test_handles_llm_failure_gracefully(
        self, mock_resolve_rule, mock_call_llm,
        sample_rules_path, mock_text, mock_outline, mock_company,
    ):
        """When the LLM returns a non-Pydantic result or None, rules get empty values."""
        from indicators_client import _llm_extract_section, set_registry_path
        from indicators_models import get_registry

        set_registry_path(sample_rules_path)
        reg = get_registry()

        rules = [
            r for r in json.loads(sample_rules_path.read_text())
            if r["module"] == "balance_sheet"
        ]

        model_class = reg["balance_sheet"]

        def mock_resolve(rname):
            return next((r for r in rules if r["name"] == rname), None)

        mock_resolve_rule.side_effect = mock_resolve

        # LLM returns a dict instead of a Pydantic model instance
        mock_call_llm.return_value = {"资产总计": 100.0}

        results = _llm_extract_section(
            rules, mock_text, mock_outline, mock_company, "auto", mock_text,
        )

        # Should still produce results for all three rules, but only one with value
        assert len(results) == 3
        by_name = {r["name"]: r for r in results}
        assert by_name["资产总计"]["value"] == 100.0
        assert by_name["负债合计"]["value"] is None
        assert by_name["所有者权益合计"]["value"] is None

    @patch("indicators_client.call_llm_pydantic")
    @patch("indicators_client.resolve_rule")
    def test_handles_llm_exception_gracefully(
        self, mock_resolve_rule, mock_call_llm,
        sample_rules_path, mock_text, mock_outline, mock_company,
    ):
        """When call_llm_pydantic raises, results get None values."""
        from indicators_client import _llm_extract_section, set_registry_path

        set_registry_path(sample_rules_path)

        rules = [
            r for r in json.loads(sample_rules_path.read_text())
            if r["module"] == "balance_sheet"
        ]

        def mock_resolve(rname):
            return next((r for r in rules if r["name"] == rname), None)

        mock_resolve_rule.side_effect = mock_resolve
        mock_call_llm.side_effect = RuntimeError("API down")

        results = _llm_extract_section(
            rules, mock_text, mock_outline, mock_company, "auto", mock_text,
        )

        assert len(results) == 3
        for r in results:
            assert r["value"] is None

    @patch("indicators_client.call_llm_pydantic")
    @patch("indicators_client.resolve_rule")
    def test_passes_correct_system_user_prompts(
        self, mock_resolve_rule, mock_call_llm,
        sample_rules_path, mock_text, mock_outline, mock_company,
    ):
        """Verify system and user prompts are constructed correctly."""
        from indicators_client import _llm_extract_section, set_registry_path
        from indicators_models import get_registry

        set_registry_path(sample_rules_path)
        reg = get_registry()

        rules = [
            r for r in json.loads(sample_rules_path.read_text())
            if r["module"] == "balance_sheet"
        ]

        model_class = reg["balance_sheet"]

        def mock_resolve(rname):
            return next((r for r in rules if r["name"] == rname), None)

        mock_resolve_rule.side_effect = mock_resolve
        mock_call_llm.return_value = _fake_pydantic_instance(model_class, {
            "资产总计": 100.0,
            "负债合计": 50.0,
            "所有者权益合计": 50.0,
        })

        _llm_extract_section(
            rules, mock_text, mock_outline, mock_company, "auto", mock_text,
        )

        call_args = mock_call_llm.call_args
        system = call_args.kwargs["system"]
        user = call_args.kwargs["user"]

        # System prompt should reference the module
        assert "balance_sheet" in system.lower() or "报表" in system
        # User prompt should contain the section text
        assert mock_text in user


class TestResolveRuleValueWithLLM:
    """Test _resolve_rule_value with report-type rules that use LLM."""

    @patch("indicators_client.call_llm_pydantic")
    @patch("indicators_client.resolve_rule")
    def test_report_rule_uses_llm(
        self, mock_resolve_rule, mock_call_llm,
        sample_rules_path, mock_text, mock_outline, mock_company,
    ):
        """A report rule with extractor=llm should go through _llm_extract_section."""
        from indicators_client import _resolve_rule_value, set_registry_path
        from indicators_models import get_registry

        set_registry_path(sample_rules_path)
        reg = get_registry()
        all_rules = json.loads(sample_rules_path.read_text())

        # Find the 资产总计 rule (balance_sheet module, extractor=llm)
        rule = next(r for r in all_rules if r["name"] == "资产总计")
        assert rule["source_type"] == "report"

        model_class = reg["balance_sheet"]

        def mock_resolve(rname):
            return next((r for r in all_rules if r["name"] == rname), None)

        mock_resolve_rule.side_effect = mock_resolve

        # Mock call_llm_pydantic to return all three balance_sheet indicators
        # because _llm_extract_section groups ALL report rules by module
        mock_call_llm.return_value = _fake_pydantic_instance(model_class, {
            "资产总计": 100.0,
            "负债合计": 50.0,
            "所有者权益合计": 50.0,
        })

        # Build a mock ctx
        from indicators_client import _Ctx
        ctx = _Ctx(
            company=mock_company,
            filing={},
            text=mock_text,
            outline=mock_outline,
            year=2025,
            period="annual",
            form="年度报告",
            extractor_mode="auto",
        )
        # Add page_offsets for section resolution
        ctx.page_offsets = [0, len(mock_text)]

        res = _resolve_rule_value(rule, ctx)
        assert res["value"] == 100.0
        assert res.get("unit") is not None
        assert "llm" in res.get("extractor", "")


class TestExtractIndicatorsLLM:
    """End-to-end tests for extract_indicators with LLM extraction."""

    @patch("indicators_client.call_llm_pydantic")
    @patch("indicators_client.resolve_rule")
    @patch("indicators_client._build_ctx")
    def test_extract_indicators_returns_dataframe(
        self, mock_build_ctx, mock_resolve_rule, mock_call_llm,
        sample_rules_path, mock_text, mock_outline, mock_company,
    ):
        """extract_indicators should return a 'dataframe' key with list of dicts."""
        from indicators_client import extract_indicators, set_registry_path, _Ctx
        from indicators_models import get_registry

        set_registry_path(sample_rules_path)
        reg = get_registry()
        all_rules = json.loads(sample_rules_path.read_text())

        def mock_resolve(rname):
            return next((r for r in all_rules if r["name"] == rname), None)

        mock_resolve_rule.side_effect = mock_resolve

        ctx = _Ctx(
            company=mock_company,
            filing={"announcement_id": "test123"},
            text=mock_text,
            outline=mock_outline,
            year=2025,
            period="annual",
            form="年度报告",
            extractor_mode="auto",
        )
        ctx.page_offsets = [0, len(mock_text)]
        mock_build_ctx.return_value = (ctx, None)

        # One call per module
        call_count = [0]
        bs_model = reg["balance_sheet"]
        is_model = reg["income_statement"]

        def mock_llm(system, user, model_class, **kwargs):
            call_count[0] += 1
            if model_class is bs_model:
                return _fake_pydantic_instance(bs_model, {
                    "资产总计": 100.0,
                    "负债合计": 50.0,
                    "所有者权益合计": 50.0,
                })
            elif model_class is is_model:
                return _fake_pydantic_instance(is_model, {
                    "营业收入": 100.0,
                    "营业支出": 70.0,
                    "营业利润": 30.0,
                    "净利润": 30.0,
                })
            return None

        mock_call_llm.side_effect = mock_llm

        result = extract_indicators("000001", year=2025)

        assert "dataframe" in result
        df = result["dataframe"]
        assert isinstance(df, list)
        assert len(df) == 7  # All 7 rules from sample

        # Each row should have the expected fields
        for row in df:
            assert "indicator" in row
            assert "value" in row
            assert "unit" in row
            assert "note" in row
            assert "stock_code" in row
            assert "company_name" in row
            assert "year" in row

        # Check specific values
        by_name = {row["indicator"]: row for row in df}
        assert by_name["资产总计"]["value"] == 100.0
        assert by_name["营业收入"]["value"] == 100.0


# ── test the test fixtures ─────────────────────────────────────────────


class TestFixtures:
    def test_sample_rules_load(self, sample_rules):
        assert len(sample_rules) == 7

    def test_registry_rebuild(self, sample_rules_path):
        from indicators_models import rebuild_registry, get_registry

        reg = rebuild_registry(sample_rules_path)
        assert "balance_sheet" in reg
        assert "income_statement" in reg

        bs = reg["balance_sheet"]
        fields = bs.model_fields
        assert "资产总计" in fields
        assert "负债合计" in fields
        assert "所有者权益合计" in fields

        # Metadata fields should be excluded from JSON schema
        from indicators_models import model_to_json_schema
        schema = model_to_json_schema(bs)
        assert "资产总计" in schema["properties"]
        assert "section" not in schema["properties"]
        assert "page" not in schema["properties"]

    def test_fake_pydantic_instance(self, sample_rules_path):
        from indicators_models import rebuild_registry

        reg = rebuild_registry(sample_rules_path)
        bs = reg["balance_sheet"]
        inst = _fake_pydantic_instance(bs, {
            "资产总计": 100.0,
            "负债合计": 50.0,
            "所有者权益合计": 50.0,
        })
        assert inst.资产总计 == 100.0
        assert inst.负债合计 == 50.0

        dumped = inst.model_dump()
        assert dumped["资产总计"] == 100.0
