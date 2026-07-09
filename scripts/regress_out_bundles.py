#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _metrics(bundle: dict) -> dict:
    missing = bundle.get("missing") or []
    unresolved = bundle.get("unresolved") or []
    indicators = bundle.get("indicators") or {}
    nulls = 0
    report_nulls = 0
    for _, v in indicators.items():
        if not isinstance(v, dict):
            continue
        if v.get("value") is None:
            nulls += 1
            if v.get("source_type") == "report":
                report_nulls += 1
    return {
        "missing": len(missing),
        "unresolved": len(unresolved),
        "nulls": nulls,
        "report_nulls": report_nulls,
    }


def main(argv: list[str]) -> int:
    baseline = Path(argv[1]) if len(argv) > 1 else (_REPO_ROOT / "out_baseline")
    current = Path(argv[2]) if len(argv) > 2 else (_REPO_ROOT / "out")

    if not baseline.exists():
        print(f"baseline dir not found: {baseline}")
        print("usage: regress_out_bundles.py <baseline_dir> [current_dir]")
        return 2
    if not current.exists():
        print(f"current dir not found: {current}")
        return 2

    base_files = {p.name: p for p in baseline.glob("*.json")}
    cur_files = {p.name: p for p in current.glob("*.json")}
    names = sorted(set(base_files.keys()) & set(cur_files.keys()))
    if not names:
        print("no overlapping bundle filenames to compare")
        return 0

    deltas = []
    for name in names:
        b = _metrics(_load(base_files[name]))
        c = _metrics(_load(cur_files[name]))
        delta = {k: c[k] - b[k] for k in b.keys()}
        deltas.append({"bundle": name, "baseline": b, "current": c, "delta": delta})

    totals = {"missing": 0, "unresolved": 0, "nulls": 0, "report_nulls": 0}
    for d in deltas:
        for k in totals.keys():
            totals[k] += d["delta"][k]

    print(f"baseline={baseline} current={current} compared={len(deltas)}")
    print("total delta:", json.dumps(totals, ensure_ascii=False))
    for d in deltas[:20]:
        print(d["bundle"], json.dumps(d["delta"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

