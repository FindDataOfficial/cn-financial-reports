from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_DEFAULT_PATH = Path(__file__).resolve().parent / "docs" / "report_section_map.json"
_SECTION_MAP_PATH: Path = _DEFAULT_PATH
_CACHE: Optional[dict] = None

_FORM_COMPAT_KEY: dict[str, str] = {
    "年度报告": "年报",
    "半年度报告": "半年报",
    "第一季度报告": "季报",
    "第三季度报告": "季报",
    "年报": "年报",
    "半年报": "半年报",
    "季报": "季报",
}


def set_section_map_path(path: str | Path) -> None:
    global _SECTION_MAP_PATH, _CACHE
    _SECTION_MAP_PATH = Path(path)
    _CACHE = None


def load_section_map(*, force: bool = False) -> dict:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    if not _SECTION_MAP_PATH.exists():
        _CACHE = {"version": 1, "forms": {}}
        return _CACHE
    data = json.loads(_SECTION_MAP_PATH.read_text(encoding="utf-8"))
    _validate_section_map(data)
    _CACHE = data
    return data


def candidates(form: str, key_or_title: str) -> list[str]:
    raw = (key_or_title or "").strip()
    if not raw:
        return []
    data = load_section_map()
    forms = data.get("forms") or {}
    compat = _FORM_COMPAT_KEY.get(form, form)
    mapping = forms.get(compat) or {}
    aliases = mapping.get(raw)
    if not aliases:
        return [raw]
    ordered: list[str] = []
    seen: set[str] = set()
    for s in [raw] + list(aliases):
        t = (s or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        ordered.append(t)
    return ordered or [raw]


def canonical_keys(form: str) -> list[str]:
    data = load_section_map()
    forms = data.get("forms") or {}
    compat = _FORM_COMPAT_KEY.get(form, form)
    mapping = forms.get(compat) or {}
    return sorted(list(mapping.keys()))


def _validate_section_map(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("report_section_map.json: root must be an object")
    forms = data.get("forms")
    if forms is None:
        return
    if not isinstance(forms, dict):
        raise ValueError("report_section_map.json: forms must be an object")
    for form_key, form_map in forms.items():
        if not isinstance(form_map, dict):
            raise ValueError(f"report_section_map.json: forms.{form_key} must be an object")
        for canon, aliases in form_map.items():
            if not isinstance(canon, str) or not canon.strip():
                raise ValueError(f"report_section_map.json: empty canonical key under {form_key}")
            if not isinstance(aliases, list) or not aliases:
                raise ValueError(f"report_section_map.json: forms.{form_key}.{canon} must be a non-empty array")
            for a in aliases:
                if not isinstance(a, str) or not a.strip():
                    raise ValueError(f"report_section_map.json: forms.{form_key}.{canon} contains empty alias")

