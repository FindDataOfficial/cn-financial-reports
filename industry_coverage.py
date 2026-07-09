"""Coverage checks for industry/document_type rule readiness."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import select

import cnreport_database
from cnreport_models import LlmRule, ScriptRule


def default_baseline_path() -> Path:
    return Path(__file__).resolve().parent / "docs" / "industry_indicator_baseline.json"


def load_baselines(path: str | Path | None = None) -> dict[str, list[str]]:
    p = Path(path) if path is not None else default_baseline_path()
    raw = json.loads(p.read_text(encoding="utf-8"))
    baselines = raw.get("baselines") if isinstance(raw, dict) else None
    if not isinstance(baselines, dict):
        raise ValueError("baseline file must contain top-level { baselines: {document_type: [indicators...] } }")
    out: dict[str, list[str]] = {}
    for dt, inds in baselines.items():
        if not isinstance(dt, str) or not dt.strip():
            continue
        if not isinstance(inds, list):
            continue
        out[dt.strip()] = [str(x).strip() for x in inds if str(x).strip()]
    return out


def _session():
    return cnreport_database.get_db().get_session()


def existing_llm_indicators(document_type: str) -> set[str]:
    dt = (document_type or "").strip()
    if not dt:
        return set()
    with _session() as session:
        rows = session.execute(
            select(LlmRule.indicator).where(LlmRule.document_type == dt)
        ).all()
    return {r[0] for r in rows if r and r[0]}


def existing_script_indicators(document_type: str) -> set[str]:
    dt = (document_type or "").strip()
    if not dt:
        return set()
    with _session() as session:
        rows = session.execute(
            select(ScriptRule.indicator).where(ScriptRule.document_type == dt)
        ).all()
    return {r[0] for r in rows if r and r[0]}


@dataclass(frozen=True)
class CoverageReport:
    document_type: str
    declared: list[str]
    missing_llm_rules: list[str]
    missing_script_rules: list[str]

    @property
    def llm_ready(self) -> bool:
        return not self.missing_llm_rules

    @property
    def script_ready(self) -> bool:
        return not self.missing_script_rules

    @property
    def supported(self) -> bool:
        return self.llm_ready and self.script_ready


def check_coverage(
    document_type: str,
    declared_indicators: Iterable[str],
) -> CoverageReport:
    declared = [str(x).strip() for x in declared_indicators if str(x).strip()]
    llm_have = existing_llm_indicators(document_type)
    script_have = existing_script_indicators(document_type)
    missing_llm = [ind for ind in declared if ind not in llm_have]
    missing_script = [ind for ind in declared if ind not in script_have]
    return CoverageReport(
        document_type=document_type,
        declared=declared,
        missing_llm_rules=missing_llm,
        missing_script_rules=missing_script,
    )


def check_from_baselines(
    *,
    document_type: str,
    baseline_path: str | Path | None = None,
) -> CoverageReport:
    baselines = load_baselines(baseline_path)
    declared = baselines.get(document_type, [])
    return check_coverage(document_type, declared)

