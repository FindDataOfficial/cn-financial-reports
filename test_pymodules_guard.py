"""Guardrail: every ``*_client.py`` and ``official_client_utils.py`` at the
package root MUST be listed in ``[tool.setuptools] py-modules``.

``fd-cn-report`` is a flat ``py-modules`` package (not a package tree), so a
top-level module missing from ``py-modules`` silently does NOT ship in the
wheel. This test fails the build before that happens. Run with the rest of the
suite: ``uv run --with pytest python -m pytest test_pymodules_guard.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_PYPROJECT = _ROOT / "pyproject.toml"


def _load_pymodules() -> set[str]:
    text = _PYPROJECT.read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+

        data = tomllib.loads(text)
        mods = data.get("tool", {}).get("setuptools", {}).get("py-modules", [])
        return set(mods)
    except ModuleNotFoundError:
        # Python 3.10 fallback: parse the [tool.setuptools] py-modules block.
        m = re.search(r"\[tool\.setuptools\]\s*\n(.*?)(?=\n\[|\Z)", text, re.S)
        block = m.group(1) if m else ""
        return set(re.findall(r'"([^"]+)"', block))


def _root_client_modules() -> set[str]:
    """Every ``*_client.py`` at the package root, plus the shared utils module.

    Excludes ``test_*`` files (e.g. ``test_sse_client.py``) which happen to end
    in ``_client.py`` but are tests, not shippable modules.
    """
    mods = {p.stem for p in _ROOT.glob("*_client.py") if not p.name.startswith("test_")}
    mods.add("official_client_utils")
    return mods


def test_every_client_module_is_listed_in_pymodules():
    listed = _load_pymodules()
    missing = _root_client_modules() - listed
    assert not missing, (
        "these root modules are NOT in [tool.setuptools] py-modules and would "
        f"not ship in the wheel: {sorted(missing)}. Add them to pyproject.toml."
    )
