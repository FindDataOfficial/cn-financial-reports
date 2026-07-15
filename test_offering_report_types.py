"""Tests for the offering/HK report types added by the add-offering-report-types change.

Covers: _FORM_COMPAT_KEY coverage, _form_compatible disjointness between
prospectus/HK and periodic forms, the prospectus/HK section maps, CNINFO
招股说明书->首发 resolution, and the period-parameterized LLM system prompt.

All tests are network-free and need no LLM_API_KEY.
"""
from __future__ import annotations

import cninfo_client
import indicators_client
import report_section_map


# ── 7.1/7.2: form-compat keys + disjointness ───────────────────────


def test_form_compat_keys_cover_new_types():
    new = ("招股说明书", "港股全球发售", "港股年度报告")
    for k in new:
        assert k in indicators_client._FORM_COMPAT_KEY
        assert k in report_section_map._FORM_COMPAT_KEY
    assert report_section_map._FORM_COMPAT_KEY["港股年度报告"] == "港股年度报告"
    assert indicators_client._FORM_COMPAT_KEY["港股年度报告"] == "港股年度报告"


def test_form_compatible_prospectus_disjoint_from_periodic():
    # A prospectus rule is skipped for periodic forms and vice versa.
    prospectus_rule = {"report_type": "招股说明书"}
    assert indicators_client._form_compatible(prospectus_rule, "年度报告") is False
    assert indicators_client._form_compatible(prospectus_rule, "第一季度报告") is False
    assert indicators_client._form_compatible(prospectus_rule, "招股说明书") is True

    periodic_rule = {"report_type": "年报/半年报/季报"}
    assert indicators_client._form_compatible(periodic_rule, "招股说明书") is False
    assert indicators_client._form_compatible(periodic_rule, "港股全球发售") is False
    assert indicators_client._form_compatible(periodic_rule, "年度报告") is True

    hk_annual_rule = {"report_type": "港股年度报告"}
    assert indicators_client._form_compatible(hk_annual_rule, "港股年度报告") is True
    assert indicators_client._form_compatible(hk_annual_rule, "年度报告") is False


def test_form_compatible_no_report_type_is_universal():
    rule = {}
    for form in ("年度报告", "招股说明书", "港股全球发售", "港股年度报告"):
        assert indicators_client._form_compatible(rule, form) is True


# ── 7.3: prospectus / HK section maps ──────────────────────────────


def test_section_map_prospectus_resolves_aliases():
    cands = report_section_map.candidates("招股说明书", "募集资金运用")
    assert cands[0] == "募集资金运用"
    assert len(cands) > 1  # at least one alias
    assert "募集資金運用" in cands


def test_section_map_hk_global_offering_resolves():
    cands = report_section_map.candidates("港股全球发售", "风险因素")
    assert "风险因素" in cands
    assert "Risk Factors" in cands


def test_section_map_hk_annual_resolves_traditional():
    cands = report_section_map.candidates("港股年度报告", "财务报表")
    assert "財務報表" in cands  # Traditional alias
    cands_bs = report_section_map.candidates("港股年度报告", "资产负债表")
    assert "財務狀況表" in cands_bs


def test_section_map_new_forms_have_canonical_keys():
    assert "募集资金运用" in report_section_map.canonical_keys("招股说明书")
    assert "募集资金用途" in report_section_map.canonical_keys("港股全球发售")
    assert "财务报表" in report_section_map.canonical_keys("港股年度报告")


# ── 3.1/3.2: CNINFO prospectus resolution ──────────────────────────


def test_resolve_category_prospectus_maps_to_shoufa():
    assert cninfo_client.resolve_category("招股说明书") == "category_sf_szsh"
    assert cninfo_client.resolve_category("首发") == "category_sf_szsh"
    # periodic resolution unchanged
    assert cninfo_client.resolve_category("年度报告") == "category_ndbg_szsh"


def test_form_from_title_recognizes_prospectus():
    assert cninfo_client._form_from_title("某某公司首次公开发行股票招股说明书") == "招股说明书"
    # periodic titles still resolve
    assert cninfo_client._form_from_title("某某公司2023年年度报告") == "年度报告"


# ── 7.5: period-parameterized, report-type-agnostic LLM prompt ─────


def test_llm_system_prompt_uses_requested_year_not_hardcoded():
    from indicators_client import _build_llm_system_prompt

    prompt = _build_llm_system_prompt("财务报表", "annual", 2024, '["资产总计"]')
    assert "2024" in prompt
    assert "2023" not in prompt
    assert "annual-report" not in prompt  # no document-type assertion


def test_llm_system_prompt_no_year_still_has_no_hardcoded_year():
    from indicators_client import _build_llm_system_prompt

    prompt = _build_llm_system_prompt("风险因素", "annual", None, '["主要风险因素"]')
    assert "2023" not in prompt
    assert "annual-report" not in prompt


# ── 7.4: baseline-concept coverage of generated prospectus rules ──


def test_zsg_prospectus_rules_cover_baseline_concepts():
    """The generated 招股说明书 rules should cover the baseline prospectus concepts.

    Rule names from the LLM need not match the baseline names verbatim, so we
    match by concept substrings. Skips when the rules DB has no 招股说明书 rules
    (e.g. CI without the generated seed).
    """
    import pytest
    import rules_db

    rules = [r for r in rules_db.load_rules()["rules"] if r.get("report_type") == "招股说明书"]
    if not rules:
        pytest.skip("no 招股说明书 rules in DB (run the pdf-llm-rules-creator generator)")

    names = [r.get("name", "") for r in rules]

    def has(*keys: str) -> bool:
        return any(any(k in n for k in keys) for n in names)

    concepts = {
        "发行价": ("发行价格", "发行价"),
        "发行股数": ("发行股数", "发行股票数量"),
        "募集资金": ("募集资金",),
        "净利润": ("净利润",),
        "营业收入": ("营业收入",),
        "总资产/权益": ("总资产", "资产总计", "股东权益", "净资产"),
        "风险因素": ("风险",),
        "主营业务": ("主营业务",),
        "实际控制人": ("实际控制人", "控股股东"),
    }
    missing = [c for c, keys in concepts.items() if not has(*keys)]
    assert not missing, f"招股说明书 rules missing concepts: {missing}"


def test_hk_annual_rules_cover_baseline_concepts():
    """The generated 港股年度报告 rules should cover the HK annual-report concepts."""
    import pytest
    import rules_db

    rules = [r for r in rules_db.load_rules()["rules"] if r.get("report_type") == "港股年度报告"]
    if not rules:
        pytest.skip("no 港股年度报告 rules in DB (run the pdf-llm-rules-creator generator)")

    names = [r.get("name", "") for r in rules]

    def has(*keys):
        return any(any(k in n for k in keys) for n in names)

    concepts = {
        "净利润/全面收益": ("净利润", "全面收益", "Profit"),
        "总资产": ("总资产", "资产总额", "Total Asset"),
        "净资产/权益": ("净资产", "股东权益", "权益总额"),
        "经营活动现金流": ("经营活动", "经营现金流", "Operating"),
        "每股股息": ("每股股息", "股息", "Dividend"),
        "主要股东": ("主要股东", "Substantial", "股东"),
        "董事": ("董事", "Director"),
    }
    missing = [c for c, keys in concepts.items() if not has(*keys)]
    assert not missing, f"港股年度报告 rules missing concepts: {missing}"
