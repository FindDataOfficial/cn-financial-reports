#!/usr/bin/env python3
"""Generate LLM indicator rules per chapter from a whole PDF.

Skill 2 of the fd-cnreport-*-creator family. Splits a PDF by its parsed
outline into chapters, generates LLM rules per chapter, validates with
pydantic, and persists to the rules database + this skill's scripts/ dir.

Usage::

    python .claude/skills/fd-cnreport-pdf-llm-rules-creator/scripts/generate_pdf_llm_rules.py \
        --pdf path/to/report.pdf --document-type 年报
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import rules_db  # noqa: E402
from rules_skills import LlmRulesOutput, chapters_from_pdf, generate_and_persist  # noqa: E402

SKILL_NAME = "fd-cnreport-pdf-llm-rules-creator"


def chapter_prompt(title: str, text: str, document_type: str) -> tuple[str, str]:
    system = (
        "You extract financial indicator rules from one chapter of a financial "
        f"report (document_type '{document_type}'). For each indicator in the "
        "chapter, produce a rule with: indicator (Chinese name), instruction "
        "(how to extract the value), position (section/selector), document_type "
        f"('{document_type}'), and any module/applies_to/unit/period_type you can "
        "infer. Return JSON: {\"rules\": [...]}."
    )
    user = (
        f"Document type: {document_type}\nChapter: {title}\n\n"
        f"Chapter text:\n{text[:12000]}\n\n"
        "Return a JSON object {\"rules\": [...]} with one entry per indicator."
    )
    return system, user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", required=True, help="Path/URL to the report PDF.")
    parser.add_argument("--document-type", default="年报", help="Report type tag (default: 年报).")
    parser.add_argument("--sleep", type=float, default=3.0,
                        help="Seconds to pause between chapters (rate-limit backoff, default 3).")
    parser.add_argument("--max-retries", type=int, default=5,
                        help="LLM retries per chapter (default 5).")
    args = parser.parse_args(argv)

    import time
    chapters = chapters_from_pdf(args.pdf)
    total = 0
    n = len(chapters)
    for i, (title, text) in enumerate(chapters, 1):
        if not text.strip():
            continue
        system, user = chapter_prompt(title, text, args.document_type)
        try:
            result = generate_and_persist(
                system, user, LlmRulesOutput, rules_db.upsert_llm_rule, SKILL_NAME,
                max_retries=args.max_retries,
            )
            print(f"chapter '{title}': {result['count']} rules")
            total += result["count"]
        except Exception as e:  # noqa: BLE001 - one bad chapter must not abort the PDF
            print(f"chapter '{title}': skipped ({e})")
        if i < n and args.sleep > 0:
            time.sleep(args.sleep)
    print(f"generated {total} LLM rules from {n} chapters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
