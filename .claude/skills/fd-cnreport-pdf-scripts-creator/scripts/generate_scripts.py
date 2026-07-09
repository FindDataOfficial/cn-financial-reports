#!/usr/bin/env python3
"""Generate script rules from a single indicator's LLM rules in the DB.

Skill 3 of the fd-cnreport-*-creator family. Reads the LLM rule(s) for one
indicator from the rules database, asks the LLM to produce a script rule
(extract_rule + position), validates with pydantic, and persists to the
rules database + this skill's scripts/ dir.

Usage::

    python .claude/skills/fd-cnreport-pdf-scripts-creator/scripts/generate_scripts.py \
        --indicator 资产总计
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import rules_db  # noqa: E402
import script_extractors  # noqa: E402
from rules_skills import ScriptRulesOutput, generate_and_persist  # noqa: E402

SKILL_NAME = "fd-cnreport-pdf-scripts-creator"


def _read_llm_rules_for(indicator: str) -> list[dict]:
    """Read llm_rules rows matching ``indicator`` (any document_type)."""
    from cnreport_models import LlmRule

    rows: list[dict] = []
    with rules_db._session() as session:
        for row in session.query(LlmRule).filter(LlmRule.indicator == indicator).all():
            rows.append(row.to_rule_dict())
    return rows


def build_prompts(indicator: str, llm_rules: list[dict]) -> tuple[str, str]:
    import json

    available = ", ".join(script_extractors.names())
    system = (
        "You choose a deterministic extractor for a financial indicator. "
        f"Available extractors: {available}. For the given LLM rule, pick the "
        "best extract_rule, copy/adapt the position (selectors), and set the "
        "document_type. Return JSON: {\"rules\": [{indicator, extract_rule, "
        "position, document_type, ...}]}."
    )
    user = (
        f"Indicator: {indicator}\n\n"
        f"LLM rules:\n{json.dumps(llm_rules, ensure_ascii=False, indent=2)[:6000]}\n\n"
        "Return a JSON object {\"rules\": [...]} with one script rule for this indicator."
    )
    return system, user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--indicator", required=True, help="Indicator name whose LLM rules to read.")
    args = parser.parse_args(argv)

    llm_rules = _read_llm_rules_for(args.indicator)
    if not llm_rules:
        print(f"no llm_rules found for indicator: {args.indicator}")
        return 1
    system, user = build_prompts(args.indicator, llm_rules)
    result = generate_and_persist(
        system, user, ScriptRulesOutput, rules_db.upsert_script_rule, SKILL_NAME,
    )
    print(f"generated {result['count']} script rules; saved to {result['saved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
