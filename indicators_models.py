"""Pydantic models for per-section LLM extraction with structured output.

Each report module (balance_sheet, income_statement, cashflow, report_section)
has a dynamically-generated Pydantic model whose fields are the indicator names
from ``indicator_rules.json``.  Adding or removing an indicator is a one-line
edit in the JSON — no Python code change needed.

Usage::

    model = model_for_module("balance_sheet")   # → BalanceSheetResult
    schema = model_to_json_schema(model)        # → dict for json_schema
    instance = model.model_validate(response)    # → validated result
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, create_model

# ── paths ─────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_RULES_PATH = _HERE / "indicator_rules.json"
"""Migration-seed path only — rules are read from the rules database at
runtime (see :mod:`rules_db`). Kept for reference/migration."""


# ── lazy model registry ───────────────────────────────────────────

_MODEL_REGISTRY_CACHE: dict[str, type] | None = None
"""Cached registry built from the rules database. Cleared on demand."""

_REPORT_MODULES = {"balance_sheet", "income_statement", "cashflow", "report_section"}


def rebuild_registry(rules_path: Path | None = None) -> dict[str, type]:
    """Force rebuild of the Pydantic model registry and return it.

    With ``rules_path`` given, seeds the rules database from that file first
    (so ``load_rules`` and the models agree), then builds. Without a path,
    builds from the current rules database. ``indicators_client.set_registry_path``
    calls this (no path) after seeding; tests call it with a fixture path.
    """
    global _MODEL_REGISTRY_CACHE
    if rules_path is not None:
        import rules_db

        rules_db.seed_rules_from_json(rules_path)
    _MODEL_REGISTRY_CACHE = _build_registry()
    return _MODEL_REGISTRY_CACHE


def _build_registry() -> dict[str, type]:
    """Build model registry from the rules database (via :mod:`rules_db`)."""
    import rules_db

    rules = rules_db.load_rules().get("rules", [])
    groups: dict[str, list[dict]] = {}
    for r in rules:
        mod = r.get("module", "unknown")
        groups.setdefault(mod, []).append(r)
    registry: dict[str, type] = {}
    for mod in _REPORT_MODULES:
        mod_rules = groups.get(mod, [])
        if mod_rules:
            registry[mod] = _build_module_model(mod, mod_rules)
    return registry


def get_registry() -> dict[str, type]:
    """Return the model registry, building it lazily if needed."""
    global _MODEL_REGISTRY_CACHE
    if _MODEL_REGISTRY_CACHE is None:
        _MODEL_REGISTRY_CACHE = _build_registry()
    return _MODEL_REGISTRY_CACHE


# ── base model ─────────────────────────────────────────────────────

class BaseExtractionResult(BaseModel):
    """Every per-section extraction model inherits from this.

    ``section`` / ``page`` / ``source`` are metadata fields set by the
    pipeline after the LLM returns.  They are NOT sent to the LLM.
    """

    section: str = ""
    page: Optional[int] = None
    source: str = ""


# ── dynamic model builder ──────────────────────────────────────────

_FIELD_CONSTRAINTS: dict[str, dict[str, Any]] = {
    # maps indicator name → extra Field kwargs (e.g. ge=0, le=1e15)
    # Populated from ``indicator_rules.json`` ``value_range`` when present.
}


def _build_model(name: str, fields: dict[str, type]) -> type[BaseExtractionResult]:
    """Build a Pydantic model with the given ``fields``.

    ``fields`` is a dict of ``indicator_name → (type, Field(...))``.
    """
    return create_model(name, __base__=BaseExtractionResult, **fields)


def _field_from_rule(r: dict) -> tuple[str, tuple]:
    """Convert a single rule dict into a ``(field_name, (type, Field(...)))`` pair."""
    name = r["name"]
    kwargs: dict[str, Any] = {"default": None, "le": 10_000_000_000_000}
    vrange = r.get("value_range")
    if isinstance(vrange, dict):
        if "min" in vrange:
            kwargs["ge"] = vrange["min"]
        if "max" in vrange:
            kwargs["le"] = vrange["max"]
    note = r.get("note") or ""
    aliases = r.get("aliases") or []
    desc_parts = [note] if note else []
    if aliases:
        desc_parts.append(f"Alias: {', '.join(aliases[:3])}")
    if desc_parts:
        kwargs["description"] = " | ".join(desc_parts)
    return name, (Optional[Decimal], Field(**kwargs))


def _build_module_model(module: str, rules: list[dict]) -> type[BaseExtractionResult]:
    """Build a Pydantic model for one report module.

    Each rule becomes an ``Optional[Decimal]`` field with sensible
    range constraints and a ``description`` copied from the rule's
    ``note`` or ``aliases`` (so the LLM sees it in the JSON Schema).
    """
    field_defs: dict[str, tuple] = {}
    for r in rules:
        fname, fdef = _field_from_rule(r)
        field_defs[fname] = fdef
    # CamelCase the module name for the class
    class_name = "".join(part.title() for part in module.replace("-", "_").split("_")) + "Result"
    return _build_model(class_name, field_defs)


def model_for_subgroup(module: str, subgroup: str, rules: list[dict]) -> type[BaseExtractionResult]:
    """Build a Pydantic model for a subgroup of indicators within a module.

    Each rule becomes an ``Optional[Decimal]`` field. The resulting model is
    scoped to just these indicators, keeping the JSON Schema small so the LLM
    can focus on relevant fields and is less likely to hallucinate.
    """
    field_defs: dict[str, tuple] = {}
    for r in rules:
        fname, fdef = _field_from_rule(r)
        field_defs[fname] = fdef
    safe = "".join(c for c in subgroup if c.isalnum() or c in ("_", " "))
    class_name = "".join(part.title() for part in module.replace("-", "_").split("_"))
    if safe.strip():
        class_name += "_" + "".join(part.title() for part in safe.strip().split())
    class_name += "Result"
    return _build_model(class_name, field_defs)


# ── convenience accessors (use lazy registry) ─────────────────────

def MODEL_REGISTRY() -> dict[str, type]:
    """Return all module → model mappings (lazy-built)."""
    return get_registry()


def model_for_module(module: str) -> type[BaseExtractionResult] | None:
    """Return the Pydantic model for ``module``, or ``None``.

    Only ``balance_sheet``, ``income_statement``, ``cashflow``, and
    ``report_section`` have registered models.
    """
    return get_registry().get(module)


def model_to_json_schema(model: type[BaseExtractionResult]) -> dict:
    """Convert a Pydantic model to a JSON Schema dict.

    The schema uses direct (Chinese) field names as property keys.
    Description annotations are kept so the LLM sees them.

    Returns an OpenAI ``json_schema``-compatible dict with ``strict=True``.
    Fields are emitted as ``{"type": "number"}`` (no ``anyOf`` with string
    patterns that some providers reject in strict mode); the caller handles
    ``Decimal`` conversion after ``model_validate``.
    """
    raw = model.model_json_schema()
    raw_props = raw.get("properties", {})
    indicator_names: list[str] = []
    props: dict[str, dict] = {}
    for field_name, field_info in model.model_fields.items():
        if field_name in ("section", "page", "source"):
            continue  # metadata not sent to LLM
        indicator_names.append(field_name)
        entry: dict = {"anyOf": [{"type": "number"}, {"type": "null"}]}
        # Pydantic stores Ge/Le in the field_info metadata in v2
        for m in field_info.metadata:
            if hasattr(m, "ge") and m.ge is not None:
                entry["minimum"] = m.ge
            if hasattr(m, "le") and m.le is not None:
                entry["maximum"] = m.le
        desc = raw_props.get(field_name, {}).get("description", "")
        if desc:
            entry["description"] = desc
        props[field_name] = entry
    return {
        "name": model.__name__,
        "schema": {
            "type": "object",
            "properties": props,
            "required": indicator_names,
            "additionalProperties": False,
        },
        "strict": True,
    }


def rules_hash(module: str | None = None) -> str:
    """Return a hash of the field set for cache-busting.

    When ``module`` is ``None``, hashes every registered module.
    """
    import hashlib

    h = hashlib.sha256()
    for mod, model in get_registry().items():
        if module is not None and mod != module:
            continue
        schema = model_to_json_schema(model)
        h.update(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()[:16]
