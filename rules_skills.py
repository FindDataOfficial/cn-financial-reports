"""Shared helpers for the ``fd-cnreport-*-creator`` generator skills.

Each skill generates LLM rules or script rules via the LLM, validates the
output with pydantic, and persists to the rules database + the skill's own
``scripts/`` directory. This module centralizes the call→validate→persist
loop so each skill script is a thin CLI wrapper.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, Type

from pydantic import BaseModel, Field

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import cnreport_tools as T  # noqa: E402
import rules_db  # noqa: E402
from rules_models import LlmRuleModel, ScriptRuleModel  # noqa: E402


class LlmRulesOutput(BaseModel):
    """LLM output model: a list of LLM rules."""

    rules: list[LlmRuleModel] = Field(default_factory=list)


class ScriptRulesOutput(BaseModel):
    """LLM output model: a list of script rules."""

    rules: list[ScriptRuleModel] = Field(default_factory=list)


def generate_and_persist(
    system: str,
    user: str,
    output_model: Type[BaseModel],
    upsert_fn: Callable[[dict], dict],
    skill_name: str,
    *,
    max_retries: int = 3,
) -> dict:
    """Call the LLM, validate against ``output_model``, upsert each rule, save.

    ``upsert_fn`` is ``rules_db.upsert_llm_rule`` or ``rules_db.upsert_script_rule``.
    Returns ``{"count": N, "saved": <path>}``. Raises if the LLM response is not
    valid JSON or fails pydantic validation — the caller decides whether to retry.
    """
    raw = T.call_llm_json(system, user, max_retries=max_retries)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM did not return valid JSON: {e}\n--- raw (first 500 chars) ---\n{raw[:500]}"
        ) from None
    validated = output_model.model_validate(data)
    rules = getattr(validated, "rules", [])
    persisted = [upsert_fn(r.model_dump(exclude_none=False)) for r in rules]
    saved = rules_db.save_to_skill_scripts_dir(skill_name, persisted)
    return {"count": len(persisted), "saved": str(saved)}


def chapters_from_pdf(pdf_path: str | Path) -> list[tuple[str, str]]:
    """Split a PDF into ``(title, text)`` chapters by its parsed outline.

    Uses ``report_cache.get_or_fetch`` for text + outline, then slices the text
    by each top-level outline entry's page (via ``page_offsets``). Falls back to
    a single whole-text chapter if the outline is empty or slicing fails.
    """
    import report_cache

    text, info = report_cache.get_or_fetch(str(pdf_path))
    outline = info.get("enriched_outline") or info.get("outline") or []
    page_offsets: list[int] = info.get("page_offsets") or []

    # top-level entries (level <= 1, or any entry with a page)
    top = [e for e in outline if (e.get("level", 1) or 1) <= 1 and "page" in e]
    if not top:
        top = [e for e in outline if "page" in e]
    if not top:
        return [(Path(pdf_path).stem, text)]

    def _slice(page: int) -> tuple[int, int]:
        """Return ``(start_offset, end_offset)`` for a 1-based page."""
        if not page_offsets:
            return 0, len(text)
        idx = max(0, (page or 1) - 1)
        start = page_offsets[idx] if idx < len(page_offsets) else 0
        return start, len(text)

    chapters: list[tuple[str, str]] = []
    for i, entry in enumerate(top):
        title = entry.get("title") or f"chapter_{i + 1}"
        start, _ = _slice(entry.get("page", 1))
        if i + 1 < len(top):
            end_start, _ = _slice(top[i + 1].get("page", 1))
            end = end_start
        else:
            end = len(text)
        chapters.append((title, text[start:end]))
    return chapters
