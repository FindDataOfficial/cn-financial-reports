---
name: fd-cnreport-pdf-scripts-creator
description: Read a single indicator/document's LLM rules from the rules database and generate script rules (extract_rule, position, document_type) for them via the LLM. Validates with pydantic and persists to the rules database + this skill's scripts/ dir.
license: MIT
metadata:
  author: cnreport
  version: "1.0"
---

# fd-cnreport-pdf-scripts-creator

Read a single indicator's LLM rules from the rules database and generate
**script rules** (`extract_rule`, `position`, `document_type`) for them.

## How to use

```bash
python .claude/skills/fd-cnreport-pdf-scripts-creator/scripts/generate_scripts.py \
  --indicator 资产总计
```

- `--indicator` — the indicator name whose LLM rule(s) to read from the
  `llm_rules` table.

The script reads the matching `llm_rules` row(s), asks the LLM to produce a
script rule (which deterministic extractor to use — e.g. `regex_amount`,
`percent_value`, `table_row`, `headcount` — and the section `position`), and
validates + upserts the result into the `script_rules` table.

## Persistence

- **Rules database** (`script_rules` table) — runtime source of truth.
- **`scripts/fd-cnreport-pdf-scripts-creator.json`** — serialized copy.

The `extract_rule` must name a registered extractor (see `script_extractors.py`);
an unregistered name yields `{value: null}` at extraction time (no crash).
