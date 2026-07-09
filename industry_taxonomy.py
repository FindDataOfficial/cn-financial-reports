"""Industry/company taxonomy and document_type helpers.

This is a thin, explicit layer around the existing rule-generation pipeline.
It standardizes how we name `document_type` for multi-industry scaling:

  cn/<industry>/<company_type>/<report_kind>
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel, Field, field_validator

_KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _is_kebab(s: str) -> bool:
    return bool(_KEBAB_RE.match(s or ""))


class IndustrySpec(BaseModel):
    industry: str = Field(..., min_length=1)
    label: str = Field(default="")
    company_types: list[str] = Field(default_factory=list)
    report_kinds: list[str] = Field(default_factory=list)

    @field_validator("industry")
    @classmethod
    def _industry_kebab(cls, v: str) -> str:
        v = (v or "").strip()
        if not _is_kebab(v):
            raise ValueError("industry must be kebab-case (lowercase)")
        return v

    @field_validator("company_types", "report_kinds")
    @classmethod
    def _kebab_list(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v or []:
            item = (item or "").strip()
            if not item:
                continue
            if not _is_kebab(item):
                raise ValueError("taxonomy identifiers must be kebab-case (lowercase)")
            out.append(item)
        return out


class IndustryTaxonomy(BaseModel):
    version: int = 1
    defaults: dict = Field(default_factory=dict)
    industries: list[IndustrySpec] = Field(default_factory=list)


def default_taxonomy_path() -> Path:
    return Path(__file__).resolve().parent / "docs" / "industry_taxonomy.json"


def load_taxonomy(path: str | Path | None = None) -> IndustryTaxonomy:
    p = Path(path) if path is not None else default_taxonomy_path()
    data = json.loads(p.read_text(encoding="utf-8"))
    return IndustryTaxonomy.model_validate(data)


def make_document_type(
    industry: str,
    company_type: str,
    report_kind: str,
    *,
    country: str = "cn",
) -> str:
    industry = (industry or "").strip()
    company_type = (company_type or "").strip()
    report_kind = (report_kind or "").strip()
    country = (country or "").strip() or "cn"
    for name, val in (("industry", industry), ("company_type", company_type), ("report_kind", report_kind)):
        if not _is_kebab(val):
            raise ValueError(f"{name} must be kebab-case (lowercase): {val!r}")
    if not _is_kebab(country):
        raise ValueError(f"country must be kebab-case (lowercase): {country!r}")
    return f"{country}/{industry}/{company_type}/{report_kind}"


@dataclass(frozen=True)
class DocumentTypeEntry:
    industry: str
    company_type: str
    report_kind: str
    document_type: str
    label: str = ""


def list_document_types(
    taxonomy: IndustryTaxonomy,
    *,
    industry: Optional[str] = None,
) -> list[DocumentTypeEntry]:
    want = (industry or "").strip() or None
    out: list[DocumentTypeEntry] = []
    defaults = taxonomy.defaults or {}
    country = (defaults.get("country") or "cn").strip() or "cn"
    default_company_types: Iterable[str] = defaults.get("company_types") or []
    default_report_kinds: Iterable[str] = defaults.get("report_kinds") or []

    for ind in taxonomy.industries:
        if want and ind.industry != want:
            continue
        company_types = ind.company_types or list(default_company_types)
        report_kinds = ind.report_kinds or list(default_report_kinds)
        for ct in company_types:
            for rk in report_kinds:
                dt = make_document_type(ind.industry, ct, rk, country=country)
                out.append(
                    DocumentTypeEntry(
                        industry=ind.industry,
                        company_type=ct,
                        report_kind=rk,
                        document_type=dt,
                        label=ind.label or "",
                    )
                )
    return out

