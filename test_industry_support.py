import json
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "industry_support.db"
    monkeypatch.setenv("DAAS_DATABASE_URL", f"sqlite:///{db}")
    import cnreport_database
    import rules_db

    cnreport_database.reset_db()
    rules_db._RULES_CACHE = None
    yield db


def test_make_document_type_and_list_entries():
    import industry_taxonomy as IT

    dt = IT.make_document_type("801780", "listed", "annual-report")
    assert dt == "cn/801780/listed/annual-report"

    tax = IT.load_taxonomy()
    assert tax.classification == "shenwan-l1-2021"
    assert len(tax.industries) == 31
    rows = IT.list_document_types(tax, industry="801780")
    assert rows
    assert rows[0].industry == "801780"
    assert any(r.document_type == "cn/801780/listed/annual-report" for r in rows)


def test_invalid_taxonomy_identifier_rejected(tmp_path):
    import industry_taxonomy as IT

    bad = {
        "version": 2,
        "classification": "shenwan-l1-2021",
        "defaults": {"country": "cn"},
        "industries": [
            {"industry": "bank", "company_types": ["listed"], "report_kinds": ["annual-report"]}
        ],
    }
    path = tmp_path / "bad_taxonomy.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(Exception):
        IT.load_taxonomy(path)


def test_coverage_report_and_supported_flag(fresh_db, tmp_path):
    import industry_coverage as C
    import rules_db

    baseline = {
        "version": 2,
        "baselines": {
            "cn/801780/listed/annual-report": ["资产总计", "净利润"]
        },
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    rep1 = C.check_from_baselines(
        document_type="cn/801780/listed/annual-report",
        baseline_path=baseline_path,
    )
    assert rep1.supported is False
    assert rep1.missing_llm_rules == ["资产总计", "净利润"]
    assert rep1.missing_script_rules == ["资产总计", "净利润"]

    rules_db.upsert_llm_rule(
        {
            "indicator": "资产总计",
            "instruction": "extract assets",
            "position": "资产负债表",
            "document_type": "cn/801780/listed/annual-report",
        }
    )
    rules_db.upsert_llm_rule(
        {
            "indicator": "净利润",
            "instruction": "extract profit",
            "position": "利润表",
            "document_type": "cn/801780/listed/annual-report",
        }
    )
    rules_db.upsert_script_rule(
        {
            "indicator": "资产总计",
            "extract_rule": "regex_amount",
            "position": "资产负债表",
            "document_type": "cn/801780/listed/annual-report",
        }
    )
    rules_db.upsert_script_rule(
        {
            "indicator": "净利润",
            "extract_rule": "regex_amount",
            "position": "利润表",
            "document_type": "cn/801780/listed/annual-report",
        }
    )

    rep2 = C.check_from_baselines(
        document_type="cn/801780/listed/annual-report",
        baseline_path=baseline_path,
    )
    assert rep2.llm_ready is True
    assert rep2.script_ready is True
    assert rep2.supported is True


def test_industry_scoped_llm_rule_requires_instruction(fresh_db):
    import rules_db

    with pytest.raises(ValueError):
        rules_db.upsert_llm_rule(
            {
                "indicator": "资产总计",
                "instruction": "",
                "position": "资产负债表",
                "document_type": "cn/801780/listed/annual-report",
            }
        )


def test_seed_support_report_script_outputs_expected_shape(fresh_db, tmp_path):
    import json
    import subprocess
    import sys

    seed = {"version": 2, "document_types": ["cn/801780/listed/annual-report"]}
    baseline = {
        "version": 2,
        "baselines": {"cn/801780/listed/annual-report": ["资产总计"]},
    }
    seed_path = tmp_path / "seed.json"
    baseline_path = tmp_path / "baseline.json"
    out_path = tmp_path / "report.json"
    seed_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/industry_support_report.py",
            "--seed-file",
            str(seed_path),
            "--baseline",
            str(baseline_path),
            "--output",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent,
    )
    assert proc.returncode == 2
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["seed_count"] == 1
    assert payload["all_supported"] is False
    assert payload["items"][0]["document_type"] == "cn/801780/listed/annual-report"

