"""Industry/company taxonomy and document_type helpers.

This is a thin, explicit layer around the existing rule-generation pipeline.
Industry identifiers use Shenwan (申万) level-1 index codes (2021 edition),
e.g. ``801780`` for 银行. ``document_type`` follows:

  cn/<sw_index_code>/<company_type>/<report_kind>
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel, Field, field_validator

_KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SW_L1_RE = re.compile(r"^801\d{3}$")


def _is_kebab(s: str) -> bool:
    return bool(_KEBAB_RE.match(s or ""))


def _is_sw_l1_code(s: str) -> bool:
    return bool(_SW_L1_RE.match(s or ""))


class IndustrySpec(BaseModel):
    industry: str = Field(..., min_length=1)
    label: str = Field(default="")
    company_types: list[str] = Field(default_factory=list)
    report_kinds: list[str] = Field(default_factory=list)

    @field_validator("industry")
    @classmethod
    def _industry_sw_code(cls, v: str) -> str:
        v = (v or "").strip()
        if not _is_sw_l1_code(v):
            raise ValueError("industry must be a Shenwan L1 index code (801xxx)")
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
    classification: str = Field(default="shenwan-l1-2021")
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
    if not _is_sw_l1_code(industry):
        raise ValueError(f"industry must be a Shenwan L1 index code (801xxx): {industry!r}")
    for name, val in (("company_type", company_type), ("report_kind", report_kind)):
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
    country: Optional[str] = None,
) -> list[DocumentTypeEntry]:
    want_industry = (industry or "").strip() or None
    countries: list[str] = []
    if country:
        countries = [country.strip()]
    else:
        defaults_country = (taxonomy.defaults or {}).get("country") or "cn"
        countries = [defaults_country, "hk"]

    out: list[DocumentTypeEntry] = []
    defaults = taxonomy.defaults or {}
    default_company_types: Iterable[str] = defaults.get("company_types") or []
    default_report_kinds: Iterable[str] = defaults.get("report_kinds") or []

    for ind in taxonomy.industries:
        if want_industry and ind.industry != want_industry:
            continue
        company_types = ind.company_types or list(default_company_types)
        report_kinds = ind.report_kinds or list(default_report_kinds)
        for cntry in countries:
            for ct in company_types:
                for rk in report_kinds:
                    dt = make_document_type(ind.industry, ct, rk, country=cntry)
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

