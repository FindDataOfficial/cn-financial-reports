#!/usr/bin/env python3
"""Generate a full end-to-end extraction script for one document_type.

Skill 5 of the fd-cnreport-*-creator family. Reads the LLM + script rules for
a document_type from the rules database, asks the LLM to emit a runnable Python
extraction script covering every indicator, validates the output with
pydantic, and writes the script to this skill's ``scripts/`` dir.

Usage::

    python .claude/skills/fd-cnreport-pdf-full-scripts-creator/scripts/generate_full_scripts.py \
        --document-type 年报/半年报/季报
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import cnreport_tools as T  # noqa: E402
import rules_db  # noqa: E402

SKILL_NAME = "fd-cnreport-pdf-full-scripts-creator"


class FullScriptOutput(BaseModel):
    """Validated output of the full-script generator."""

    document_type: str = Field(..., min_length=1)
    indicators: list[str] = Field(default_factory=list)
    script: str = Field(..., min_length=1)

    @field_validator("script")
    @classmethod
    def _is_python(cls, v: str) -> str:
        if "import" not in v or "def " not in v:
            raise ValueError("script does not look like a Python module (missing import/def)")
        return v


def _read_rules(document_type: str) -> tuple[list[dict], list[dict]]:
    from cnreport_models import LlmRule, ScriptRule

    llm: list[dict] = []
    script: list[dict] = []
    with rules_db._session() as session:
        for row in (
            session.query(LlmRule).filter(LlmRule.document_type == document_type).all()
        ):
            llm.append(row.to_rule_dict())
        for row in (
            session.query(ScriptRule).filter(ScriptRule.document_type == document_type).all()
        ):
            script.append(row.to_rule_dict())
    return llm, script


def build_prompts(document_type: str, llm_rules: list[dict], script_rules: list[dict]) -> tuple[str, str]:
    system = (
        "You generate a self-contained Python extraction script for a set of "
        "financial indicators. The script MUST: import `rules_db` and "
        "`indicators_client`; define a `main(ticker_or_name, year)` that calls "
        "`indicators_client.extract_indicators(...)` for the document_type "
        f"'{document_type}'; and print a JSON bundle. Return JSON: "
        '{{"document_type": ..., "indicators": ["indicator_name_1", "indicator_name_2", ...], '
        '"script": "<python source>"}}.'
    )
    indicators = [{"indicator": r["name"], "module": r.get("module")} for r in llm_rules]
    user = (
        f"document_type: {document_type}\n"
        f"indicators ({len(indicators)}): {json.dumps(indicators, ensure_ascii=False)[:4000]}\n"
        f"existing script_rules: {len(script_rules)}\n\n"
        "Generate the full extraction script. Return a JSON object with "
        "'document_type', 'indicators' (list of indicator name strings only, no dicts), "
        "and 'script' (Python source)."
    )
    return system, user


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "doctype"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--document-type", required=True, help="document_type to cover.")
    args = parser.parse_args(argv)

    llm_rules, script_rules = _read_rules(args.document_type)
    if not llm_rules and not script_rules:
        print(f"no rules found for document_type: {args.document_type}")
        return 1
    system, user = build_prompts(args.document_type, llm_rules, script_rules)

    raw = T.call_llm_json(system, user)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"LLM did not return valid JSON: {e}\n{raw[:400]}")
        return 1
    out = FullScriptOutput.model_validate(data)

    skill_scripts = Path(__file__).resolve().parent
    script_path = skill_scripts / f"full_extraction_{_slug(out.document_type)}.py"
    script_path.write_text(out.script, encoding="utf-8")
    manifest = {
        "document_type": out.document_type,
        "indicators": out.indicators,
        "script_path": str(script_path),
    }
    manifest_path = rules_db.save_to_skill_scripts_dir(SKILL_NAME, manifest)
    print(f"generated full script for {out.document_type}: {len(out.indicators)} indicators")
    print(f"script: {script_path}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
