#!/usr/bin/env python3
"""Generate LLM indicator rules from a section excerpt of a document.

Skill 1 of the fd-cnreport-*-creator family. Reads a piece of a document,
asks the LLM to produce LLM rules (indicator, instruction, position,
document_type), validates with pydantic, and persists to the rules database +
this skill's scripts/ dir.

Usage::

    python .claude/skills/fd-cnreport-llm-rules-creator/scripts/generate_llm_rules.py \
        --text path/to/section.txt --document-type 年报
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import rules_db  # noqa: E402
from rules_skills import LlmRulesOutput, generate_and_persist  # noqa: E402

SKILL_NAME = "fd-cnreport-llm-rules-creator"


def build_prompts(text: str, document_type: str) -> tuple[str, str]:
    system = (
        "You extract financial indicator rules from Chinese annual-report text. "
        "For each indicator you can identify in the excerpt, produce a rule with: "
        "indicator (the Chinese name), instruction (how to extract the value from "
        "the report), position (the section/selector where it appears), "
        f"document_type (use '{document_type}'), and any of module/applies_to/unit/"
        "period_type you can infer. Return JSON: {\"rules\": [...]}."
    )
    user = (
        f"Document type: {document_type}\n\n"
        f"Excerpt:\n{text[:12000]}\n\n"
        "Return a JSON object {\"rules\": [...]} with one entry per indicator."
    )
    return system, user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--text", required=True, help="Path to a section excerpt text file.")
    parser.add_argument("--document-type", default="年报", help="Report type tag (default: 年报).")
    args = parser.parse_args(argv)

    text = Path(args.text).read_text(encoding="utf-8")
    system, user = build_prompts(text, args.document_type)
    result = generate_and_persist(
        system, user, LlmRulesOutput, rules_db.upsert_llm_rule, SKILL_NAME,
    )
    print(f"generated {result['count']} LLM rules; saved to {result['saved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
