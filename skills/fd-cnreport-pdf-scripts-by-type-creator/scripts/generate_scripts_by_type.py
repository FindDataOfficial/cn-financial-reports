#!/usr/bin/env python3
"""Generate a script rule per indicator for one document_type.

Skill 4 of the fd-cnreport-*-creator family. Reads every LLM rule for a
document_type from the rules database, asks the LLM to produce one script rule
per indicator, validates with pydantic, and persists to the rules database +
this skill's scripts/ dir.

Usage::

    python .claude/skills/fd-cnreport-pdf-scripts-by-type-creator/scripts/generate_scripts_by_type.py \
        --document-type 年报/半年报/季报
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

SKILL_NAME = "fd-cnreport-pdf-scripts-by-type-creator"


def _read_llm_rules_by_type(document_type: str) -> list[dict]:
    from cnreport_models import LlmRule

    rows: list[dict] = []
    with rules_db._session() as session:
        for row in (
            session.query(LlmRule)
            .filter(LlmRule.document_type == document_type)
            .order_by(LlmRule.module, LlmRule.indicator)
            .all()
        ):
            rows.append(row.to_rule_dict())
    return rows


def build_prompts(document_type: str, llm_rules: list[dict]) -> tuple[str, str]:
    import json

    available = ", ".join(script_extractors.names())
    system = (
        "You choose a deterministic extractor per financial indicator. "
        f"Available extractors: {available}. For each indicator in the list, "
        "produce one script rule: extract_rule (one of the available names), "
        "position (selectors), document_type, indicator. Return JSON: "
        "{\"rules\": [...]}."
    )
    user = (
        f"document_type: {document_type}\n\n"
        f"Indicators ({len(llm_rules)}):\n"
        + json.dumps(
            [{"indicator": r["name"], "module": r.get("module"), "unit": r.get("unit"),
              "position": r.get("position")} for r in llm_rules],
            ensure_ascii=False, indent=2,
        )[:12000]
        + "\n\nReturn a JSON object {\"rules\": [...]} with one script rule per indicator."
    )
    return system, user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--document-type", required=True, help="document_type to read from llm_rules.")
    args = parser.parse_args(argv)

    llm_rules = _read_llm_rules_by_type(args.document_type)
    if not llm_rules:
        print(f"no llm_rules found for document_type: {args.document_type}")
        return 1
    system, user = build_prompts(args.document_type, llm_rules)
    result = generate_and_persist(
        system, user, ScriptRulesOutput, rules_db.upsert_script_rule, SKILL_NAME,
    )
    print(f"generated {result['count']} script rules for {len(llm_rules)} indicators; saved to {result['saved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
