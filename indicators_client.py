"""Indicator rules engine for cnreport-mcp.

Loads the data-driven rule set (``indicator_rules.json``), profiles a company
to decide which rules apply, and resolves indicator values via three source
strategies — akshare line items, annual-report PDF sections (LLM or pluggable
Python extractors), and locally-computed ratios.

Mirrors the load/resolve pattern of ``cninfo_client`` (data-driven JSON,
no code change to add a rule) and the cache pattern of ``report_cache``.

Public entry points (used by cnreport_tools + the standalone script)::

    load_rules() / resolve_rule(name) / list_rules(module, query, company)
    profile_company(stock_code, name) / applicable_rules(stock_code, name)
    get_indicator(indicator, ticker_or_name, year, period)
    extract_indicators(ticker_or_name, year, indicators, form, extractor_mode)
    render_methodology()            # → markdown string
    rules_hash(rules)               # cache-busting digest

Errors at the public boundary are returned as ``{"error": ...}`` by the
``@_tool_safe`` wrappers in ``cnreport_tools``; this module raises freely.
"""
from __future__ import annotations

import hashlib
import logging
import os
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

_REGISTRY_PATH = Path(__file__).resolve().parent / "indicator_rules.json"
_RULES_CACHE: Optional[dict] = None

# ── bank sub-type lookup ──────────────────────────────────────────
# Curated ticker → sub_type for the listed Chinese banks. Name-keyword
# heuristic is the fallback for tickers not listed here.
_BANK_SUBTYPE_BY_TICKER: dict[str, str] = {
    # 国有大行
    "601398": "国有大行", "601939": "国有大行", "601288": "国有大行",
    "601988": "国有大行", "601328": "国有大行", "601658": "国有大行",
    # 股份制
    "600000": "股份制", "600015": "股份制", "600016": "股份制",
    "600036": "股份制", "601166": "股份制", "601318": "股份制",
    "601818": "股份制", "601998": "股份制", "600999": "股份制",
    "000001": "股份制",
}

_SUBTYPE_BY_NAME_KEYWORD = (
    (("城市", "城商", "银行股份"), "城商行"),
    (("农村", "农商", "农信"), "农商行"),
)


# ── rule loading + name resolution ────────────────────────────────


def load_rules() -> dict:
    """Load and cache the indicator rule set (indicator_rules.json).

    Returns ``{_schema, rules: [...]}``. Raises ``FileNotFoundError`` if the
    registry is missing and ``json.JSONDecodeError`` if malformed — both naming
    the file, so a misconfigured package fails loudly at first use.
    """
    global _RULES_CACHE
    if _RULES_CACHE is not None:
        return _RULES_CACHE
    if not _REGISTRY_PATH.exists():
        raise FileNotFoundError(f"indicator rule set not found: {_REGISTRY_PATH}")
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"malformed indicator rule set {_REGISTRY_PATH}: {e.msg}", e.doc, e.pos
        ) from None
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise ValueError(f"indicator rule set {_REGISTRY_PATH}: missing 'rules' array")
    _RULES_CACHE = data
    return data


def set_registry_path(path) -> None:
    """Point the engine at a different rule file and clear the cache.

    Used by the standalone extraction script (``--rules``) so different
    companies can be processed against different rule sets in separate runs.
    """
    global _REGISTRY_PATH, _RULES_CACHE
    _REGISTRY_PATH = Path(path)
    _RULES_CACHE = None


def _rules() -> list[dict]:
    return load_rules().get("rules", [])


def rules_hash(rules: Optional[list[dict]] = None) -> str:
    """Stable 16-char sha1 of the rule set — used to bust the indicator bundle cache."""
    rs = rules if rules is not None else _rules()
    return hashlib.sha1(
        json.dumps(rs, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def _normalize(s: str) -> str:
    """Strip whitespace + common punctuation for tolerant Chinese name matching."""
    return re.sub(r"[\s　·、，,。.：:（）()\-_/]", "", (s or ""))


def resolve_rule(name: str) -> Optional[dict]:
    """Resolve an indicator name to a rule: exact → alias → normalized substring."""
    if not name:
        return None
    rules = _rules()
    for r in rules:
        if r.get("name") == name:
            return r
    for r in rules:
        if name in (r.get("aliases") or []):
            return r
    target = _normalize(name)
    if not target:
        return None
    for r in rules:
        if target == _normalize(r.get("name", "")):
            return r
        for a in r.get("aliases", []):
            if target == _normalize(a):
                return r
    for r in rules:
        if target and target in _normalize(r.get("name", "")):
            return r
        for a in r.get("aliases", []):
            if target and target in _normalize(a):
                return r
    return None


def list_rules(
    module: Optional[str] = None,
    query: Optional[str] = None,
    company: Optional[str] = None,
) -> dict:
    """Return rules grouped by module, optionally filtered.

    ``module`` filters to one module; unknown module returns an error dict.
    ``query`` does a normalized substring match over name+aliases.
    ``company`` (ticker or name) filters to ``applicable_rules`` and includes
    the resolved ``{industry, sub_type}`` profile.
    """
    rules = _rules()
    profile = None
    if company is not None:
        profile, rules = _applicable_for(company, rules)

    modules = sorted({r.get("module", "") for r in rules})
    if module is not None:
        if module not in modules:
            return {"error": f"unknown module: {module!r}", "available": modules}
        rules = [r for r in rules if r.get("module") == module]

    if query:
        q = _normalize(query)
        rules = [
            r for r in rules
            if q in _normalize(r.get("name", ""))
            or any(q in _normalize(a) for a in r.get("aliases", []))
        ]

    # group by module then subgroup
    groups: dict[str, dict[str, list[dict]]] = {}
    for r in rules:
        groups.setdefault(r.get("module", ""), {}).setdefault(
            r.get("subgroup", ""), []
        ).append(_summarize_rule(r))

    result: dict[str, Any] = {
        "groups": [
            {"module": m, "subgroups": [{"subgroup": sg, "indicators": items} for sg, items in subs.items()]}
            for m, subs in groups.items()
        ],
        "count": len(rules),
    }
    if profile is not None:
        result["company_profile"] = profile
    return result


def _summarize_rule(r: dict) -> dict:
    return {
        "name": r.get("name"),
        "aliases": r.get("aliases", []),
        "module": r.get("module"),
        "subgroup": r.get("subgroup"),
        "source_type": r.get("source_type"),
        "extractor": r.get("extractor"),
        "applies_to": r.get("applies_to"),
        "unit": r.get("unit"),
        "period_type": r.get("period_type"),
    }


# ── company profiling + applicability ─────────────────────────────


def profile_company(stock_code: str, name: str = "") -> dict:
    """Classify a company as ``{industry, sub_type}``.

    Banks resolve to one of {国有大行, 股份制, 城商行, 农商行} via a curated
    ticker lookup with a name-keyword heuristic fallback. Non-banks return
    ``{industry: "unknown", sub_type: None}`` (still eligible for ``industry: "*"``
    rules).
    """
    code = (stock_code or "").strip()
    sub = _BANK_SUBTYPE_BY_TICKER.get(code)
    if sub:
        return {"industry": "bank", "sub_type": sub}
    nm = name or ""
    for keywords, st in _SUBTYPE_BY_NAME_KEYWORD:
        if any(k in nm for k in keywords):
            return {"industry": "bank", "sub_type": st}
    # 6-digit code with no match → unknown (could be a non-bank A-share)
    return {"industry": "unknown", "sub_type": None}


def _company_profile_from_lookup(stock_code: str, name: str = "") -> dict:
    return profile_company(stock_code, name)


def applies_to(rule: dict, profile: dict, stock_code: str) -> bool:
    """Evaluate a rule's ``applies_to`` against a company profile + ticker."""
    ap = rule.get("applies_to") or {}
    industry = ap.get("industry", "*")
    if industry not in ("*", profile.get("industry", "unknown")):
        return False
    sub_types = ap.get("sub_types") or ["*"]
    if "*" not in sub_types and profile.get("sub_type") not in sub_types:
        return False
    companies = ap.get("companies") or ["*"]
    if "*" not in companies and stock_code not in companies:
        return False
    exclude = ap.get("exclude_companies") or []
    if stock_code in exclude:
        return False
    return True


def applicable_rules(stock_code: str, name: str = "") -> tuple[dict, list[dict]]:
    """Return ``(profile, [applicable rules])`` for a company."""
    profile = profile_company(stock_code, name)
    rules = _rules()
    return profile, [r for r in rules if applies_to(r, profile, stock_code)]


def _applicable_for(company: str, rules: list[dict]) -> tuple[dict, list[dict]]:
    """Resolve `company` (ticker or name) via cninfo and filter `rules`."""
    import cninfo_client

    row = cninfo_client.lookup_company(company)
    if not row:
        # fall back to treating the input as a raw ticker so profiling still works
        stock = company if (company or "").isdigit() else ""
        profile = profile_company(stock, company)
        return profile, [r for r in rules if applies_to(r, profile, stock)]
    stock = row.get("stock_code", "")
    profile = profile_company(stock, row.get("name", ""))
    return profile, [r for r in rules if applies_to(r, profile, stock)]


# ── source routing primitives ─────────────────────────────────────


def _value_obj(
    value: Any, *, rule: dict, source: str, extractor: str, period: str,
    provenance: str = "", note: str = "",
) -> dict:
    return {
        "indicator": rule.get("name"),
        "value": value,
        "unit": rule.get("unit", ""),
        "source_type": rule.get("source_type"),
        "extractor": extractor,
        "source": source,
        "period": period,
        "provenance": provenance,
        "note": note,
    }


def _resolve_via_akshare(company: dict, rule: dict, year: int, period: str) -> dict:
    """Read one field from akshare's structured statements."""
    import financials_client

    src = rule.get("source") or {}
    statement = src.get("statement")
    field = src.get("field")
    if not statement or not field:
        return _value_obj(
            None, rule=rule, source="akshare", extractor="akshare", period=period,
            note="akshare rule missing statement/field",
        )
    try:
        all_stmts = financials_client.get_statements(
            company["stock_code"], period=period, exchange=company.get("exchange", ""),
        )
    except financials_client.MissingDependencyError as e:
        return _value_obj(
            None, rule=rule, source="akshare", extractor="akshare", period=period,
            note=f"akshare unavailable: {e}",
        )
    stmt = all_stmts.get(statement)
    if not stmt:
        return _value_obj(
            None, rule=rule, source=f"akshare:{statement}", extractor="akshare", period=period,
            note=f"statement not returned: {statement}",
        )
    columns = stmt.get("columns", [])
    data = stmt.get("data", [])
    if field not in columns:
        # try a normalized substring match on column names
        matches = [c for c in columns if _normalize(field) in _normalize(c)]
        if not matches:
            return _value_obj(
                None, rule=rule, source=f"akshare:{statement}", extractor="akshare",
                period=period, note=f"field not in columns: {field!r}; have {columns}",
            )
        field = matches[0]
    idx = columns.index(field)
    # pick the row matching the requested year (period end -12-31)
    target = f"{year}-12-31"
    row = None
    date_col = next((c for c in ("报告日", "报告期", "日期") if c in columns), None)
    if date_col:
        for r in data:
            if str(r[columns.index(date_col)]) == target:
                row = r
                break
    if row is None and data:
        row = data[0]  # fall back to the most recent row
    if row is None:
        return _value_obj(
            None, rule=rule, source=f"akshare:{statement}.{field}", extractor="akshare",
            period=period, note="no rows in statement",
        )
    value = row[idx] if idx < len(row) else None
    return _value_obj(
        value, rule=rule, source=f"akshare:{statement}.{field}", extractor="akshare",
        period=period, provenance=f"akshare row {target}",
    )


def _resolve_section(text: str, outline: list[dict], rule: dict, stock_code: str):
    """Walk the rule's ``selectors[]`` chain; return ``(section_text, matched)``.

    Company-filtered selectors are tried first; on a miss the next entry is
    tried. Returns ``(None, [tried selectors])`` when nothing hits.
    """
    import cnreport_tools as T

    src = rule.get("source") or {}
    selectors = src.get("selectors") or []
    tried: list[str] = []
    # order: company-matching selectors first, then the rest, preserving chain order within each
    def _company_matches(sel: dict) -> bool:
        companies = sel.get("company") or []
        return (not companies) or (stock_code in companies)

    ordered = [s for s in selectors if _company_matches(s)] + [
        s for s in selectors if not _company_matches(s)
    ]
    for sel in ordered:
        section = sel.get("section")
        if not section:
            continue
        tried.append(section)
        entry = T.resolve_selector(outline, section)
        if entry is None:
            continue
        body = T.extract_section_text(text, outline, entry)
        if body:
            return body, section
    # statement-module fallback: try the canonical consolidated statement title
    # (合并资产负债表 / 合并利润表 / 合并现金流量表) via resolve_statement. This
    # honors rules whose selector is a descriptive section label that did not
    # resolve directly, and matches the get_financial_statements strategy.
    stmt_key = _MODULE_TO_STATEMENT.get(rule.get("module", ""))
    if stmt_key is not None:
        entry = T.resolve_statement(outline, stmt_key)
        if entry is not None:
            body = T.extract_section_text(text, outline, entry)
            if body:
                return body, entry.get("title", stmt_key)
    # body-text fallback for quarterly reports whose outline lacks statement
    # titles: search the raw text for the canonical statement title and slice.
    if stmt_key is not None:
        body = T.extract_statement_text(text, stmt_key)
        if body:
            return body, f"<body-text: {stmt_key}>"
    return None, tried


# rule module → statement key for resolve_statement (the consolidated-first matcher).
_MODULE_TO_STATEMENT: dict[str, str] = {
    "balance_sheet": "balance_sheet",
    "income_statement": "income_statement",
    "cashflow": "cashflow",
}

# CNINFO form name → CSV-style compat key used in a rule's `report_type` field.
# Used by `_form_compatible` to filter rules per periodic form: an annual-only
# rule (report_type "年报") is skipped for 第一季度报告, while a universal rule
# (report_type "年报/半年报/季报") applies to every form.
_FORM_COMPAT_KEY: dict[str, str] = {
    "年度报告": "年报",
    "半年度报告": "半年报",
    "第一季度报告": "季报",
    "第三季度报告": "季报",
}


def _form_compatible(rule: dict, form: str) -> bool:
    """True if `rule` should be attempted for the given periodic `form`.

    A rule without a `report_type` defaults to broadly applicable (treated as
    present in every form) — this covers hand-authored rules that pre-date the
    CSV `report_type` column. Otherwise the form's compat key (e.g. `年报`)
    must be a substring of the rule's `report_type` (e.g. `年报/半年报/季报`).
    Unknown `form` values default to compatible so callers passing raw category
    codes don't accidentally suppress extraction.
    """
    rt = rule.get("report_type")
    if not rt:
        return True
    key = _FORM_COMPAT_KEY.get(form)
    if key is None:
        return True
    return key in rt


def _llm_extract_section(
    section_text: str, rules: list[dict], period: str, *, max_chars: int | None = None,
    pdf_url: str | None = None, section_key: str | None = None,
) -> dict[str, dict]:
    """One LLM call over a section requesting every indicator in `rules`.

    Returns ``{indicator_name: {value, unit, note}}``. On any failure (no API
    key, parse error) returns one entry per rule with ``value=None`` and a note.

    When ``pdf_url`` and ``section_key`` are provided, the raw ``{records:[...]}``
    response is persisted to and read from the section cache
    (:mod:`llm_section_cache`). On a full hit (all wanted indicators present in
    the cached ``meta.wanted``) the LLM is not called; on a partial hit the
    delta is fetched and merged into the cached response.
    """
    import cnreport_tools as T
    import llm_section_cache as LSC

    if max_chars is None:
        max_chars = int(os.environ.get("LLM_MAX_CHARS", "12000"))

    cfg = T.llm_config()
    if not cfg["api_key"]:
        return {
            r["name"]: {"value": None, "unit": r.get("unit", ""), "note": "LLM_API_KEY not configured"}
            for r in rules
        }

    wanted_names = [r["name"] for r in rules]
    rh = rules_hash() if (pdf_url and section_key) else ""

    # Section cache lookup (only when caller supplied pdf_url + section_key).
    # Cache read/write are wrapped in try/except so a broken cache never blocks
    # the LLM path; on any error we fall through to a fresh LLM call.
    _log = logging.getLogger(__name__)
    cached = None
    if pdf_url and section_key:
        try:
            cached = LSC.get(pdf_url, section_key, period, rh)
        except Exception as e:
            _log.debug("section cache read error: %s", e)
            cached = None

    if cached is not None:
        cached_records = LSC.cached_subset(cached, wanted_names)
        cached_norm = {LSC._normalize_name(r.get("indicator", "")) for r in cached_records}
        wanted_norm = {LSC._normalize_name(n) for n in wanted_names}
        missing_norm = wanted_norm - cached_norm
        if not missing_norm:
            # Full hit: every wanted indicator is in the cache. No LLM call.
            return _records_to_results(cached_records, rules, note="llm-section-cache")
        # Partial hit: fetch the delta, merge, write back, return merged.
        delta_rules = [r for r in rules if LSC._normalize_name(r["name"]) in missing_norm]
        delta_out = _llm_fetch_records(section_text, delta_rules, period, max_chars)
        if "error" in delta_out:
            return _records_to_results(cached_records, rules, note="llm-section-cache")
        delta_records = list(delta_out.get("records") or [])
        merged = list(cached_records) + [
            r for r in delta_records
            if LSC._normalize_name(r.get("indicator", "")) not in cached_norm
        ]
        try:
            LSC.put(pdf_url, section_key, period, rh, merged)
        except Exception as e:
            _log.debug("section cache write error: %s", e)
        return _records_to_results(merged, rules, note="llm-section-cache")

    # Cache miss (or cache disabled / no pdf_url/section_key): call the LLM.
    fetched = _llm_fetch_records(section_text, rules, period, max_chars)
    if "error" in fetched:
        return fetched["error"]
    if pdf_url and section_key:
        try:
            LSC.put(pdf_url, section_key, period, rh, fetched.get("records") or [])
        except Exception as e:
            _log.debug("section cache write error: %s", e)
    return _records_to_results(fetched.get("records") or [], rules, note="llm")


def _llm_fetch_records(
    section_text: str, rules: list[dict], period: str, max_chars: int,
) -> dict:
    """One LLM call → ``{"records": [...]}`` or ``{"error": {name: {value:None, note}}}``.

    Pure LLM call + parse; no cache reads or writes. Returns the raw records so
    the caller can persist them, and the per-rule error map for failure paths.
    """
    import cnreport_tools as T

    snippet = section_text[:max_chars]
    wanted = []
    for r in rules:
        hint = (r.get("source") or {}).get("schema_hint") or {}
        wanted.append({"indicator": r["name"], "unit": r.get("unit", ""), **hint})

    system = (
        "You extract structured financial figures from Chinese annual-report text. "
        "For each requested indicator, return its value for the requested period. "
        "Return ONLY a JSON object with a 'records' array; one record per indicator. "
        "If an indicator is not present, set value to null. Do not include prose."
    )
    user = json.dumps({"period": period, "wanted": wanted, "text": snippet}, ensure_ascii=False)
    try:
        content = T.call_llm_json(system, user)
        data = json.loads(content)
        records = data.get("records") if isinstance(data, dict) else data
        if not isinstance(records, list):
            records = []
    except Exception as e:
        return {"error": {
            r["name"]: {"value": None, "unit": r.get("unit", ""), "note": f"llm error: {type(e).__name__}: {e}"}
            for r in rules
        }}
    return {"records": records}


def _records_to_results(
    records: list[dict], rules: list[dict], *, note: str,
) -> dict[str, dict]:
    """Map a ``{records:[{indicator,value,unit}]}`` payload to ``{name: {value, unit, note}}``.

    Missing indicators get ``value=None`` and ``note="<note>: not returned"``
    so the caller can distinguish a cache hit that was complete from one that
    had a partial LLM response originally.
    """
    by_name: dict[str, dict] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        nm = rec.get("indicator")
        if not nm:
            continue
        by_name[_normalize(nm)] = {
            "value": rec.get("value"),
            "unit": rec.get("unit") or "",
            "note": note,
        }
    out: dict[str, dict] = {}
    for r in rules:
        key = _normalize(r["name"])
        if key in by_name:
            out[r["name"]] = by_name[key]
        else:
            out[r["name"]] = {"value": None, "unit": r.get("unit", ""),
                              "note": f"{note}: not returned" if note != "llm" else "llm: not returned"}
    return out


def _run_extractor(
    section_text: str, rule: dict, period: str, extractor_mode: str = "auto",
    llm_cache: Optional[dict] = None,
    *,
    pdf_url: str | None = None,
    section_key: str | None = None,
) -> dict:
    """Dispatch one report rule to its extractor, honoring ``extractor_mode``.

    ``llm_cache`` (when provided) carries the batched LLM result for this section
    so a single indicator lookup reuses the per-section call instead of re-querying.

    When ``pdf_url`` + ``section_key`` are provided and the rule resolves to the
    LLM extractor, the persistent section cache (``llm_section_cache``) is
    consulted first. A hit returns the cached record with
    ``note: "llm-section-cache"``; a miss falls through to ``_llm_extract_section``
    and the result is written back to the cache.
    """
    declared = rule.get("extractor") or (rule.get("source") or {}).get("extractor") or "llm"
    if extractor_mode == "llm":
        effective = "llm"
    elif extractor_mode == "python":
        if declared.startswith("python:"):
            effective = declared
        else:
            return {"value": None, "unit": rule.get("unit", ""),
                    "note": "skipped: llm extractor in python mode"}
    else:  # auto
        effective = declared

    if effective == "llm":
        if llm_cache is not None and rule["name"] in llm_cache:
            return llm_cache[rule["name"]]
        result = _llm_extract_section(
            section_text, [rule], period,
            pdf_url=pdf_url, section_key=section_key,
        )
        return result.get(rule["name"], {"value": None, "unit": rule.get("unit", ""), "note": "llm: empty"})
    if effective.startswith("python:"):
        import indicators_extractors

        name = effective.split(":", 1)[1]
        fn = indicators_extractors.get(name)
        if fn is None:
            return {"value": None, "unit": rule.get("unit", ""),
                    "note": f"unknown extractor: {effective}"}
        try:
            return fn(section_text, rule, period)
        except Exception as e:
            return {"value": None, "unit": rule.get("unit", ""),
                    "note": f"extractor error: {type(e).__name__}: {e}"}
    return {"value": None, "unit": rule.get("unit", ""), "note": f"unknown extractor: {effective}"}


def _resolve_via_report(
    text: str, outline: list[dict], rule: dict, stock_code: str,
    year: int, period: str, extractor_mode: str, pdf_url: str,
    llm_cache: Optional[dict] = None,
) -> dict:
    section_text, matched = _resolve_section(text, outline, rule, stock_code)
    if section_text is None:
        return _value_obj(
            None, rule=rule, source=f"report:{matched}", extractor=rule.get("extractor", "llm"),
            period=period, provenance=pdf_url,
            note=f"section not found; tried {matched}",
        )
    res = _run_extractor(
        section_text, rule, period, extractor_mode, llm_cache=llm_cache,
        pdf_url=pdf_url, section_key=matched,
    )
    return _value_obj(
        res.get("value"), rule=rule, source=f"report:{matched}",
        extractor=res.get("note", "").startswith("llm") and "llm"
        or (rule.get("extractor") or "llm"),
        period=period, provenance=pdf_url, note=res.get("note", ""),
    )


# ── safe formula evaluator ────────────────────────────────────────

_TOK_RE = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([+\-*/()])|([^+\-*/()\s]+))")


def _eval_formula(formula: str, base_values: dict[str, Any]) -> tuple[Any, Optional[str]]:
    """Evaluate ``formula`` with ``+ - * / ()``, numeric literals, and indicator-name refs.

    Returns ``(value, None)`` on success or ``(None, "missing input: <name>")``.
    Uses Python's ``ast`` for safe parsing — no eval/exec.
    """
    import ast

    # token names referenced in the formula resolve to base_values
    def _resolve_tok(name: str) -> Any:
        if name in base_values:
            return base_values[name]
        return None

    # Replace each indicator name (Chinese token) with a placeholder var,
    # then build an ast and walk it.
    tokens: list[str] = []
    pos = 0
    while pos < len(formula):
        m = _TOK_RE.match(formula, pos)
        if not m:
            pos += 1
            continue
        pos = m.end()
        num, op, name = m.groups()
        if num is not None:
            tokens.append(num)
        elif op is not None:
            tokens.append(op)
        elif name is not None:
            tokens.append(name)
    # Now parse tokens into an expression string with names quoted as vars.
    # Build a name→symbol map to substitute, then use ast.
    expr_parts: list[str] = []
    name_map: dict[str, str] = {}
    for t in tokens:
        if t in ("+", "-", "*", "/", "(", ")"):
            expr_parts.append(t)
        elif re.fullmatch(r"\d+(?:\.\d+)?", t):
            expr_parts.append(t)
        else:
            sym = name_map.get(t)
            if sym is None:
                sym = f"__v{len(name_map)}"
                name_map[t] = sym
            expr_parts.append(sym)
    expr = " ".join(expr_parts)
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None, "formula syntax error"

    env: dict[str, float] = {}
    for original, sym in name_map.items():
        raw = _resolve_tok(original)
        if raw is None or raw == "":
            return None, f"missing input: {original}"
        try:
            env[sym] = float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            return None, f"non-numeric input: {original}={raw!r}"

    def _ev(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return _ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Name):
            return env[n.id]
        if isinstance(n, ast.BinOp):
            a, b = _ev(n.left), _ev(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if isinstance(n.op, ast.Div):
                return a / b if b != 0 else None
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -_ev(n.operand)
        raise ValueError("unsupported operation in formula")

    try:
        result = _ev(node)
    except ZeroDivisionError:
        return None, "division by zero"
    except Exception as e:
        return None, f"formula error: {e}"
    return result, None


def _resolve_via_computed(rule: dict, base_values: dict[str, Any], period: str) -> dict:
    src = rule.get("source") or {}
    formula = src.get("formula", "")
    value, err = _eval_formula(formula, base_values)
    return _value_obj(
        value, rule=rule, source=f"computed:{formula}", extractor="computed",
        period=period, note=err or "",
    )


# ── context + single-indicator resolution ─────────────────────────


class _Ctx:
    """Carries everything a resolution pass needs to avoid re-fetching."""

    def __init__(self, company, filing, text, outline, year, period, form, extractor_mode):
        self.company = company
        self.filing = filing
        self.text = text
        self.outline = outline
        self.year = year
        self.period = period
        self.form = form
        self.extractor_mode = extractor_mode
        self._section_cache: dict[str, str] = {}  # section title → body text

    @property
    def pdf_url(self) -> str:
        return (self.filing or {}).get("pdf_url", "")

    @property
    def stock_code(self) -> str:
        return (self.company or {}).get("stock_code", "")


def _resolve_rule_value(rule: dict, ctx: _Ctx, depth: int = 0) -> dict:
    """Resolve one rule (any source_type) within a context. Recurses for computed inputs."""
    if depth > 6:
        return _value_obj(None, rule=rule, source="depth", extractor="auto",
                          period=ctx.period, note="recursion depth exceeded")
    st = rule.get("source_type")
    if st == "akshare":
        return _resolve_via_akshare(ctx.company, rule, ctx.year, ctx.period)
    if st == "report":
        return _resolve_via_report(
            ctx.text, ctx.outline, rule, ctx.stock_code, ctx.year, ctx.period,
            ctx.extractor_mode, ctx.pdf_url,
        )
    if st == "computed":
        src = rule.get("source") or {}
        inputs = src.get("inputs") or []
        bases: dict[str, Any] = {}
        for inp in inputs:
            irule = resolve_rule(inp)
            if irule is None:
                bases[inp] = None
                continue
            ires = _resolve_rule_value(irule, ctx, depth + 1)
            bases[inp] = ires.get("value")
        return _resolve_via_computed(rule, bases, ctx.period)
    if st == "external":
        # realtime / market-data indicator — not present in the report PDF
        return _value_obj(
            None, rule=rule, source="external", extractor="",
            period=ctx.period, note="external source — not extractable from report",
        )
    return _value_obj(None, rule=rule, source="unknown", extractor="auto",
                      period=ctx.period, note=f"unknown source_type: {st}")


def _build_ctx(
    ticker_or_name: str, year: int, form: str, period: str, extractor_mode: str,
    *, fetch_pdf: bool = True,
) -> tuple[Optional[_Ctx], Optional[dict]]:
    """Resolve company + filing + (optionally) cached PDF text → a `_Ctx`.

    Returns ``(ctx, None)`` on success or ``(None, error_dict)`` on failure.
    """
    import cninfo_client
    import report_cache
    import cnreport_tools as T

    company = cninfo_client.lookup_company(ticker_or_name)
    if not company:
        return None, {"error": f"no company matched: {ticker_or_name!r}"}
    filings = cninfo_client.query_announcements(
        company["stock_code"], company["org_id"], form=form, year=year, limit=5,
    )
    if not filings:
        return None, {
            "error": f"no filing found for {company['stock_code']} form={form!r} year={year}"
        }
    top = filings[0]
    text = outline = None
    if fetch_pdf:
        text, _ = report_cache.get_or_fetch(
            top["pdf_url"],
            stock_code=company["stock_code"], year=year, form=form,
            announcement_id=top.get("announcement_id") or "",
        )
        outline = T.parse_outline(text)
    ctx = _Ctx(company, top, text, outline, year, period, form, extractor_mode)
    return ctx, None


# ── public entry points ───────────────────────────────────────────


def get_indicator(
    indicator: str, ticker_or_name: str, year: int, period: str = "annual",
) -> dict:
    """Resolve a single named indicator for a company + period."""
    rule = resolve_rule(indicator)
    if rule is None:
        return {"error": f"unknown indicator: {indicator!r}",
                "available": [r["name"] for r in _rules()][:30]}

    ctx, err = _build_ctx(ticker_or_name, year, "年度报告", period, "auto", fetch_pdf=False)
    if err:
        return err
    # applicability check
    profile, applicable = applicable_rules(ctx.stock_code, ctx.company.get("name", ""))
    if not any(r["name"] == rule["name"] for r in applicable):
        return {"error": "indicator not applicable to this company",
                "indicator": indicator, "company": ctx.stock_code}

    # only fetch the PDF when the rule actually needs it (report or computed-with-report-inputs)
    needs_pdf = rule["source_type"] in ("report",) or (
        rule["source_type"] == "computed"
        and _computed_needs_pdf(rule)
    )
    if needs_pdf:
        ctx2, err = _build_ctx(ticker_or_name, year, ctx.form, period, "auto", fetch_pdf=True)
        if err:
            return err
        ctx = ctx2
    res = _resolve_rule_value(rule, ctx)
    return {
        "stock_code": ctx.stock_code,
        "company_name": ctx.company.get("name", ""),
        "year": year,
        "indicator": rule["name"],
        **res,
    }


def _computed_needs_pdf(rule: dict, depth: int = 0) -> bool:
    """True if a computed rule (transitively) depends on a report-source input."""
    if depth > 6:
        return False
    for inp in (rule.get("source") or {}).get("inputs", []):
        irule = resolve_rule(inp)
        if irule is None:
            continue
        if irule["source_type"] == "report":
            return True
        if irule["source_type"] == "computed" and _computed_needs_pdf(irule, depth + 1):
            return True
    return False


def extract_indicators(
    ticker_or_name: str,
    year: int,
    indicators: Optional[list[str]] = None,
    form: str = "年度报告",
    extractor_mode: str = "auto",
) -> dict:
    """Extract many indicators for one company/year in one pass.

    Fetches the PDF once, groups report-rules by section (one LLM call per
    section), runs Python extractors individually, and computes derived ratios
    locally. Caches the resulting bundle to disk keyed by the applicable rule set.
    """
    import report_cache
    import cnreport_tools as T

    ctx, err = _build_ctx(ticker_or_name, year, form, "annual", extractor_mode, fetch_pdf=True)
    if err:
        return err
    profile, applicable = applicable_rules(ctx.stock_code, ctx.company.get("name", ""))

    # select the requested subset (after applicability)
    if indicators is None:
        target_rules = applicable
    else:
        applicable_names = {r["name"] for r in applicable}
        target_rules = []
        unknown: list[str] = []
        not_applicable: list[str] = []
        for nm in indicators:
            r = resolve_rule(nm)
            if r is None:
                unknown.append(nm)
            elif r["name"] not in applicable_names:
                not_applicable.append(nm)
            else:
                target_rules.append(r)

    rh = rules_hash(target_rules)
    stem = report_cache.cache_key(
        ctx.pdf_url, stock_code=ctx.stock_code, year=year, form=form,
        announcement_id=ctx.filing.get("announcement_id") or "",
    )
    if stem is not None:
        cached = report_cache.get_cached_indicators(stem, rh)
        if cached is not None:
            cached["cached"] = True
            return cached

    results: dict[str, dict] = {}
    missing: list[dict] = []
    unresolved: list[dict] = []
    section_cache_reuse = 0  # incremented in the LLM per-section loop below

    if indicators is not None:
        for nm in unknown:
            missing.append({"indicator": nm, "reason": "unknown"})
        for nm in not_applicable:
            missing.append({"indicator": nm, "reason": "not applicable"})

    # --- akshare group: one fetch ---
    akshare_rules = [r for r in target_rules if r["source_type"] == "akshare"]
    for r in akshare_rules:
        results[r["name"]] = _resolve_via_akshare(ctx.company, r, year, "annual")

    # --- external group: realtime/market indicators not in the report PDF → unresolved ---
    external_rules = [r for r in target_rules if r["source_type"] == "external"]
    for r in external_rules:
        unresolved.append({
            "indicator": r["name"],
            "note": "external source — not extractable from report",
        })

    # --- report group: group by resolved section, batch LLM per section ---
    report_rules = [r for r in target_rules if r["source_type"] == "report"]
    # resolve each rule's section first
    section_of: dict[str, str] = {}
    section_text_cache: dict[str, str] = {}
    for r in report_rules:
        body, matched = _resolve_section(ctx.text, ctx.outline, r, ctx.stock_code)
        if body is None:
            results[r["name"]] = _value_obj(
                None, rule=r, source=f"report:{matched}", extractor=r.get("extractor", "llm"),
                period="annual", provenance=ctx.pdf_url, note=f"section not found; tried {matched}",
            )
            missing.append({"indicator": r["name"], "reason": "section not found",
                            "tried": matched})
            continue
        section_of[r["name"]] = matched
        section_text_cache[matched] = body

    # group report rules by section + by extractor mode
    if extractor_mode == "python":
        # only python extractors run; llm rules → unresolved
        for r in report_rules:
            if r["name"] not in section_of:
                continue  # already added to missing
            sec = section_of[r["name"]]
            res = _run_extractor(section_text_cache[sec], r, "annual", "python")
            results[r["name"]] = _value_obj(
                res.get("value"), rule=r, source=f"report:{sec}",
                extractor=(r.get("extractor", "").startswith("python:") and r["extractor"] or "llm"),
                period="annual", provenance=ctx.pdf_url, note=res.get("note", ""),
            )
            if res.get("value") is None and "skipped" in (res.get("note") or ""):
                unresolved.append({"indicator": r["name"], "note": res["note"]})
    else:
        sections = sorted(set(section_of.values()))
        for sec in sections:
            rules_in_sec = [r for r in report_rules if section_of.get(r["name"]) == sec]
            llm_rules = [r for r in rules_in_sec if _effective_extractor(r, extractor_mode) == "llm"]
            python_rules = [r for r in rules_in_sec if _effective_extractor(r, extractor_mode).startswith("python:")]
            llm_cache: dict[str, dict] = {}
            if llm_rules:
                llm_cache = _llm_extract_section(
                    section_text_cache[sec], llm_rules, "annual",
                    pdf_url=ctx.pdf_url, section_key=sec,
                )
                # Count records served from the section cache.
                for r in llm_rules:
                    rec = llm_cache.get(r["name"], {})
                    if (rec.get("note") or "").startswith("llm-section-cache"):
                        section_cache_reuse += 1
            for r in llm_rules:
                rec = llm_cache.get(r["name"], {"value": None, "note": "llm: empty"})
                results[r["name"]] = _value_obj(
                    rec.get("value"), rule=r, source=f"report:{sec}", extractor="llm",
                    period="annual", provenance=ctx.pdf_url, note=rec.get("note", ""),
                )
            for r in python_rules:
                res = _run_extractor(section_text_cache[sec], r, "annual", "python")
                results[r["name"]] = _value_obj(
                    res.get("value"), rule=r, source=f"report:{sec}",
                    extractor=r.get("extractor", "python"), period="annual",
                    provenance=ctx.pdf_url, note=res.get("note", ""),
                )

    # --- computed group: evaluate from bases already in `results` ---
    computed_rules = [r for r in target_rules if r["source_type"] == "computed"]
    # multi-pass so computed rules can depend on other computed rules
    pending = list(computed_rules)
    for _ in range(len(pending) + 1):
        if not pending:
            break
        still: list[dict] = []
        for r in pending:
            src = r.get("source") or {}
            inputs = src.get("inputs") or []
            bases = {inp: (results.get(inp, {}) or {}).get("value") for inp in inputs}
            if any(bases[i] is None for i in inputs):
                # try next pass; inputs might come from another pending computed rule
                still.append(r)
                continue
            results[r["name"]] = _resolve_via_computed(r, bases, "annual")
        if len(still) == len(pending):
            # no progress → unresolved
            for r in still:
                src = r.get("source") or {}
                inputs = src.get("inputs") or []
                missing_inputs = [i for i in inputs if (results.get(i, {}) or {}).get("value") is None]
                results[r["name"]] = _value_obj(
                    None, rule=r, source=f"computed:{src.get('formula','')}", extractor="computed",
                    period="annual", note=f"missing input: {','.join(missing_inputs)}",
                )
                unresolved.append({"indicator": r["name"], "note": f"missing input: {','.join(missing_inputs)}"})
            break
        pending = still

    bundle = {
        "stock_code": ctx.stock_code,
        "company_name": ctx.company.get("name", ""),
        "industry": profile.get("industry"),
        "sub_type": profile.get("sub_type"),
        "year": year,
        "form": form,
        "pdf_url": ctx.pdf_url,
        "cached": False,
        "rules_hash": rh,
        "extractor_mode": extractor_mode,
        "indicators": results,
        "missing": missing,
        "unresolved": unresolved,
        "section_cache_reuse": section_cache_reuse,
    }
    if stem is not None:
        report_cache.write_cached_indicators(stem, bundle)
    return bundle


# ── position-CSV-driven extraction ────────────────────────────────


def _resolve_csv_path(csv_path: str) -> Path:
    """Resolve a (possibly relative) CSV path against the repo root."""
    p = Path(csv_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    return p


def load_position_csv(csv_path: str = "docs/indicators_position.csv") -> list[str]:
    """Read the ``indicator`` column of a position CSV → ordered, de-duplicated name list."""
    import csv as _csv

    p = _resolve_csv_path(csv_path)
    rows = list(_csv.DictReader(p.open(encoding="utf-8", newline="")))
    seen: set[str] = set()
    names: list[str] = []
    for r in rows:
        n = (r.get("indicator") or "").strip()
        if n and n not in seen:
            seen.add(n)
            names.append(n)
    return names


def extract_indicators_by_position(
    ticker_or_name: str,
    year: int,
    csv_path: str = "docs/indicators_position.csv",
    extractor: str = "auto",
    indicators: Optional[list[str]] = None,
    form: str = "年度报告",
) -> dict:
    """Extract the indicators named in a position CSV for one company/year/form.

    Reads the CSV's ``indicator`` column (intersected with ``indicators`` if
    given), resolves each name to a rule, partitions by ``source_type`` and
    form-applicability (``external`` → ``skipped``; form-incompatible →
    ``skipped``; everything else → delegated to ``extract_indicators`` with the
    requested ``form``), and returns the standard bundle plus a ``skipped``
    list and the ``csv_path`` used.

    ``form`` selects the periodic report (年度报告 / 半年度报告 / 第一季度报告 /
    第三季度报告). Each rule's ``report_type`` is consulted via
    ``_form_compatible`` so annual-only indicators (e.g. 分红金额) are skipped
    for quarterly forms instead of being attempted and failing.
    """
    csv_names = load_position_csv(csv_path)
    if indicators:
        wanted = set(indicators)
        csv_names = [n for n in csv_names if n in wanted]

    skipped: list[dict] = []
    missing_unknown: list[dict] = []
    delegate_names: list[str] = []
    for nm in csv_names:
        rule = resolve_rule(nm)
        if rule is None:
            missing_unknown.append({"indicator": nm, "reason": "unknown"})
        elif rule.get("source_type") == "external":
            skipped.append({
                "indicator": nm,
                "source_type": "external",
                "note": "realtime/external — not in report PDF",
            })
        elif not _form_compatible(rule, form):
            # rule's report_type doesn't include this form (e.g. 分红金额 for Q1)
            skipped.append({
                "indicator": nm,
                "source_type": "form_filter",
                "note": f"not in {form}",
            })
        else:
            delegate_names.append(rule["name"])

    if delegate_names:
        bundle = extract_indicators(
            ticker_or_name, year, indicators=delegate_names,
            form=form, extractor_mode=extractor,
        )
    else:
        # nothing to extract from the report — build a header without fetching the PDF
        ctx, err = _build_ctx(
            ticker_or_name, year, form, "annual", extractor, fetch_pdf=False,
        )
        if err:
            bundle = err
        else:
            profile = profile_company(ctx.stock_code, ctx.company.get("name", ""))
            bundle = {
                "stock_code": ctx.stock_code,
                "company_name": ctx.company.get("name", ""),
                "industry": profile.get("industry"),
                "sub_type": profile.get("sub_type"),
                "year": year,
                "form": form,
                "pdf_url": ctx.pdf_url,
                "cached": False,
                "rules_hash": rules_hash([]),
                "extractor_mode": extractor,
                "indicators": {},
                "missing": [],
                "unresolved": [],
                "section_cache_reuse": 0,
            }

    bundle["csv_path"] = str(_resolve_csv_path(csv_path))
    bundle["skipped"] = skipped
    if missing_unknown:
        bundle.setdefault("missing", []).extend(missing_unknown)
    return bundle


def _effective_extractor(rule: dict, extractor_mode: str) -> str:
    declared = rule.get("extractor") or (rule.get("source") or {}).get("extractor") or "llm"
    if extractor_mode == "llm":
        return "llm"
    if extractor_mode == "python":
        return declared if declared.startswith("python:") else "llm"
    return declared


# ── methodology renderer ──────────────────────────────────────────


def render_methodology() -> str:
    """Render the rule set as a markdown methodology document."""
    rules = _rules()
    lines: list[str] = []
    lines.append("# Indicators — source & process methodology")
    lines.append("")
    lines.append(
        "Generated from `indicator_rules.json`. Each indicator lists its source type, "
        "the concrete annual-report section selector chain (or akshare field / formula), "
        "the extractor, applicability, and a process note. `indicators.md` remains the "
        "human-authored catalog; this document is the machine-kept companion."
    )
    lines.append("")
    lines.append(f"_Total rules: {len(rules)} · rules_hash: {rules_hash(rules)}_")
    lines.append("")

    # group by module then subgroup
    by_module: dict[str, dict[str, list[dict]]] = {}
    for r in rules:
        by_module.setdefault(r.get("module", ""), {}).setdefault(
            r.get("subgroup", ""), []
        ).append(r)

    for module, subs in by_module.items():
        lines.append(f"## {module}")
        lines.append("")
        for sg, items in subs.items():
            lines.append(f"### {sg}")
            lines.append("")
            lines.append("| Indicator | source_type | source | extractor | applies_to | unit | note |")
            lines.append("|---|---|---|---|---|---|---|")
            for r in items:
                src = r.get("source") or {}
                if r["source_type"] == "akshare":
                    src_str = f"akshare `{src.get('statement')}.{src.get('field')}`"
                elif r["source_type"] == "report":
                    chain = " → ".join(
                        (s.get("section", "") + ("*" if s.get("company") else ""))
                        for s in src.get("selectors", [])
                    )
                    src_str = f"report: {chain}"
                elif r["source_type"] == "external":
                    src_str = "external (realtime/market — not in report PDF)"
                else:
                    src_str = f"computed: `{src.get('formula')}`"
                ap = r.get("applies_to") or {}
                ap_str = []
                if ap.get("industry") and ap["industry"] != "*":
                    ap_str.append(ap["industry"])
                if ap.get("sub_types") and ap["sub_types"] != ["*"]:
                    ap_str.append("/".join(ap["sub_types"]))
                if ap.get("companies") and ap["companies"] != ["*"]:
                    ap_str.append("companies:" + ",".join(ap["companies"]))
                if ap.get("exclude_companies"):
                    ap_str.append("exclude:" + ",".join(ap["exclude_companies"]))
                ap_text = " ".join(ap_str) or "*"
                note = (r.get("note") or "").replace("|", "/").replace("\n", " ")
                lines.append(
                    f"| {r['name']} | {r['source_type']} | {src_str} | "
                    f"{r.get('extractor','')} | {ap_text} | {r.get('unit','')} | {note} |"
                )
            lines.append("")

    lines.append("## Adding a new rule")
    lines.append("")
    lines.append(
        "Append an entry to `indicator_rules.json`. Required fields: `name`, `module`, "
        "`subgroup`, `applies_to`, `source_type`, and the matching `source` spec "
        "(`{statement, field}` for akshare, `{selectors:[...], extractor}` for report, "
        "`{formula, inputs}` for computed). Optional: `aliases`, `unit`, `period_type`, "
        "`direction`, `note`. No Python change is needed — `list_indicators`, "
        "`get_indicator`, `extract_indicators`, and the script all read the JSON at call "
        "time. Then re-run `python indicators_client.py --render-methodology > "
        "docs/indicators-methodology.md` to refresh this document."
    )
    lines.append("")
    lines.append("## Adding a new extractor")
    lines.append("")
    lines.append(
        "1. Write a function `(section_text, rule, period) -> {value, unit, note}` in "
        "`indicators_extractors.py`.\n"
        "2. Call `register('your_name', your_fn)` at import time.\n"
        "3. Set `\"extractor\": \"python:your_name\"` on the rule(s) that should use it.\n"
        "\n"
        "The engine dispatches by name; no engine change is required. Python extractors "
        "receive the already-sliced, cache-backed section text and never touch the PDF "
        "themselves. Use `--extractor python` on the script to run LLM-free where possible."
    )
    lines.append("")
    lines.append("## LLM section cache")
    lines.append("")
    lines.append(
        "The LLM extractor persists the raw `{records:[...]}` response to "
        "`<CNREPORT_CACHE_DIR>/llm_sections/<key>.json`, keyed by "
        "`(pdf_url, section_key, period, rules_hash)`. After a section has been "
        "extracted once, subsequent runs — including single-indicator lookups via "
        "`get_indicator` and re-runs with different indicator subsets — reuse the "
        "cached records and only re-query the LLM for indicators not yet cached.\n"
        "\n"
        "The bundle exposes a `section_cache_reuse: <int>` field that counts records "
        "served from the section cache in that run (distinct from `cached: true`, "
        "which indicates a full bundle hit). The cache is on by default; set "
        "`LLM_SECTION_CACHE=off` to disable it at runtime. CNINFO reports are "
        "immutable, so the cache is safe to leave on indefinitely."
    )
    lines.append("")
    return "\n".join(lines)


def render_coverage() -> str:
    """Render a coverage summary of the rule set as markdown.

    Companion to ``render_methodology``: a concise summary (counts by module and
    source_type, fetchable vs external) rather than a per-rule table. The full
    per-rule source/process detail lives in ``docs/indicators-methodology.md``.
    """
    rules = _rules()
    total = len(rules)
    by_module: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for r in rules:
        by_module[r.get("module", "")] = by_module.get(r.get("module", ""), 0) + 1
        st = r.get("source_type", "")
        by_source[st] = by_source.get(st, 0) + 1
    fetchable = sum(v for k, v in by_source.items() if k in ("akshare", "report", "computed"))
    external = by_source.get("external", 0)

    lines: list[str] = []
    lines.append("# Indicators coverage — implemented rule set")
    lines.append("")
    lines.append(
        "Summary of `indicator_rules.json` (the implemented rule set). Banking rules are "
        "hand-authored; the broader set is migrated from `docs/indicators_position.csv` "
        "by `scripts/migrate_indicators_csv.py`. Per-rule source/process detail lives in "
        "`docs/indicators-methodology.md`."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total rules: **{total}**")
    lines.append(f"- **Fetchable** (report / akshare / computed): **{fetchable}**")
    lines.append(f"- **External** (realtime/market — not in report PDF, listed in `skipped`): **{external}**")
    lines.append(f"- rules_hash: `{rules_hash(rules)}`")
    lines.append("")
    lines.append("## By source_type")
    lines.append("")
    lines.append("| source_type | count | meaning |")
    lines.append("|---|---|---|")
    meaning = {
        "akshare": "read from akshare structured statements",
        "report": "extracted from the annual-report PDF section",
        "computed": "derived locally from base values via a formula",
        "external": "realtime/market data — not in the report PDF",
    }
    for st in ("akshare", "report", "computed", "external"):
        lines.append(f"| {st} | {by_source.get(st, 0)} | {meaning.get(st, '')} |")
    lines.append("")
    lines.append("## By module")
    lines.append("")
    lines.append("| module | rules |")
    lines.append("|---|---|")
    for m in sorted(by_module):
        lines.append(f"| {m} | {by_module[m]} |")
    lines.append("")
    lines.append("## Refresh")
    lines.append("")
    lines.append(
        "Regenerate after editing the CSV / rules:\n\n"
        "```\n"
        "python scripts/migrate_indicators_csv.py          # sync CSV → indicator_rules.json\n"
        "python indicators_client.py --render-methodology > docs/indicators-methodology.md\n"
        "python indicators_client.py --render-coverage > docs/indicators-coverage.md\n"
        "```"
    )
    lines.append("")
    return "\n".join(lines)


def write_coverage_csv(path) -> None:
    """Write the flat coverage CSV (one row per rule) to ``path``."""
    import csv as _csv

    rules = _rules()
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["module", "subgroup", "indicator", "fetchable", "source_type", "extractor", "method"])
        for r in rules:
            st = r.get("source_type", "")
            src = r.get("source") or {}
            if st == "akshare":
                method = f"akshare ({src.get('statement')}.{src.get('field')})"
                fetchable = "yes"
            elif st == "report":
                chain = " → ".join(s.get("section", "") for s in src.get("selectors", []))
                method = f"report PDF ({r.get('extractor', 'llm')}): {chain}"
                fetchable = "yes"
            elif st == "computed":
                method = f"computed ({src.get('formula', '')})"
                fetchable = "yes"
            elif st == "external":
                method = ""
                fetchable = "no"
            else:
                method = ""
                fetchable = "no"
            w.writerow([r.get("module", ""), r.get("subgroup", ""), r.get("name", ""),
                        fetchable, st, r.get("extractor", ""), method])


def _main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Indicator rules engine CLI")
    p.add_argument("--render-methodology", action="store_true",
                   help="Print the methodology markdown to stdout")
    p.add_argument("--render-coverage", action="store_true",
                   help="Print the coverage summary markdown to stdout")
    p.add_argument("--write-coverage-csv", metavar="PATH",
                   help="Write the flat coverage CSV (one row per rule) to PATH")
    args = p.parse_args()
    if args.render_methodology:
        print(render_methodology())
    if args.render_coverage:
        print(render_coverage())
    if args.write_coverage_csv:
        write_coverage_csv(args.write_coverage_csv)


if __name__ == "__main__":
    _main()
