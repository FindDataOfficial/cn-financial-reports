"""Pluggable Python extractors for the indicator rules engine.

Each extractor is a pure function with the signature::

    fn(section_text: str, rule: dict, period: str) -> dict

returning ``{"value": <number|str|None>, "unit": <str>, "note": <str>}``.
The rules engine dispatches to a registered function when a rule declares
``extractor: "python:<name>"``. The LLM path (``extractor: "llm"``) is
handled separately in ``indicators_client`` via ``ai_extract``.

Adding a new extractor
----------------------
1. Write a function with the signature above in this file (or import it here).
2. Call ``register("your_name", your_fn)`` at import time.
3. Set ``"extractor": "python:your_name"`` on the rule in
   ``indicator_rules.json``.

No engine change is required. Extractors receive the already-sliced section
text (cache-backed) so they never touch the PDF themselves.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

# ── registry ──────────────────────────────────────────────────────

EXTRACTORS: dict[str, Callable[[str, dict, str], dict]] = {}


def register(name: str, fn: Callable[[str, dict, str], dict]) -> None:
    """Register a Python extractor under ``name`` (overwrites on re-register)."""
    EXTRACTORS[name] = fn


def get(name: str) -> Optional[Callable[[str, dict, str], dict]]:
    """Return the registered extractor, or ``None`` if not registered."""
    return EXTRACTORS.get(name)


# ── shared numeric helpers ────────────────────────────────────────

# Match a Chinese-numeric amount with optional 万/亿 scaling and a leading
# label. Captures: 1=label, 2=sign, 3=number, 4=unit-scale (万/亿), 5=%.
_NUM_RE = re.compile(
    r"([^\d：:，,。.\s]{2,20}?)\s*[:：]?\s*"
    r"([\-+]?)\s*"
    r"([\d,]+(?:\.\d+)?)"
    r"\s*(万元|亿元|万|亿|元)?"
    r"\s*(%)?"
)


def _to_float(raw: str) -> Optional[float]:
    """'1,234.56' -> 1234.56; non-numeric -> None."""
    try:
        return float(raw.replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _scale(num: float, unit: str) -> float:
    """Apply Chinese unit scaling: 万 → *1e4, 亿 → *1e8."""
    if unit and unit.startswith("亿"):
        return num * 1e8
    if unit and unit.startswith("万"):
        return num * 1e4
    return num


# ── starter extractors ────────────────────────────────────────────


def regex_amount(section_text: str, rule: dict, period: str) -> dict:
    """Locate the rule's indicator name in the section and read the adjacent number.

    Strategy: find the first line containing the indicator name (or any alias),
    then read the first numeric token on that line (or the next). Applies 万/亿
    scaling and records the unit. Returns ``value=None`` when no number is found.
    """
    name = rule.get("name", "")
    aliases = [name] + list(rule.get("aliases", []))
    unit_hint = rule.get("unit", "")

    lines = section_text.splitlines()
    for i, line in enumerate(lines):
        if not any(a and a in line for a in aliases):
            continue
        # search this line, then the next two for a number
        window = "\n".join(lines[i : i + 3])
        m = _NUM_RE.search(window)
        if not m:
            continue
        num = _to_float(m.group(3))
        if num is None:
            continue
        num = _scale(num, m.group(4) or "")
        # percent token wins over a unit hint when present
        if m.group(5) == "%":
            return {"value": num, "unit": "%", "note": f"regex_amount match on line {i+1}"}
        return {"value": num, "unit": unit_hint or m.group(4) or "", "note": f"regex_amount match on line {i+1}"}
    return {"value": None, "unit": unit_hint, "note": "regex_amount: no numeric match near indicator name"}


def percent_value(section_text: str, rule: dict, period: str) -> dict:
    """Read a percentage value for the indicator: first ``NN%`` near the name."""
    name = rule.get("name", "")
    aliases = [name] + list(rule.get("aliases", []))
    lines = section_text.splitlines()
    for i, line in enumerate(lines):
        if not any(a and a in line for a in aliases):
            continue
        window = "\n".join(lines[i : i + 3])
        m = re.search(r"([\d,]+(?:\.\d+)?)\s*%", window)
        if m:
            num = _to_float(m.group(1))
            if num is not None:
                return {"value": num, "unit": "%", "note": f"percent_value match on line {i+1}"}
    return {"value": None, "unit": "%", "note": "percent_value: no % match near indicator name"}


def table_row(section_text: str, rule: dict, period: str) -> dict:
    """Locate a row whose label matches the indicator name and read its first numeric cell.

    Tolerates table cells split by spaces / pipes / multiple spaces. Returns
    the unscaled number (no 万/亿 folding) so callers can compare raw figures.
    """
    name = rule.get("name", "")
    aliases = [name] + list(rule.get("aliases", []))
    unit_hint = rule.get("unit", "")
    for line in section_text.splitlines():
        if not any(a and a in line for a in aliases):
            continue
        # collect all numeric tokens on the line
        nums = re.findall(r"[\d,]+(?:\.\d+)?", line)
        # skip a leading ordinal like "1." or "（一）" by taking the largest parseable
        for raw in nums:
            num = _to_float(raw)
            if num is None:
                continue
            return {"value": num, "unit": unit_hint, "note": "table_row first numeric cell"}
    return {"value": None, "unit": unit_hint, "note": "table_row: no numeric cell on matching row"}


def headcount(section_text: str, rule: dict, period: str) -> dict:
    """Read a headcount: ``员工 N 人`` / ``员工总数 N`` / ``在职员工 N 人``.

    Broader than ``regex_amount`` for the common bank phrasing ``员工 419,252 人``,
    which lacks the ``员工人数`` label that ``regex_amount`` keys on. Scans the
    whole section for the first ``员工``-bearing line with a 4+ digit count.
    """
    name = rule.get("name", "")
    aliases = [name] + list(rule.get("aliases", []))
    unit_hint = rule.get("unit", "人")
    keywords = [a for a in (["员工", "从业", "人员", "职工"] + aliases) if a]
    for line in section_text.splitlines():
        if not any(k in line for k in keywords):
            continue
        m = re.search(r"([\d,]{4,})\s*人", line)
        if not m:
            continue
        num = _to_float(m.group(1))
        if num is not None:
            return {"value": num, "unit": unit_hint, "note": "headcount match"}
    return {"value": None, "unit": unit_hint, "note": "headcount: no count found"}


# ── register starters at import ───────────────────────────────────

register("regex_amount", regex_amount)
register("percent_value", percent_value)
register("table_row", table_row)
register("headcount", headcount)
