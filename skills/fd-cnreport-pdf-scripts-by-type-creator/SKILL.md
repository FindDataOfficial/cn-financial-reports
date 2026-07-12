---
name: fd-cnreport-pdf-scripts-by-type-creator
description: Read all LLM rules for a document_type from the rules database and generate a script rule per target indicator via the LLM. Validates with pydantic and persists to the rules database + this skill's scripts/ dir.
license: MIT
metadata:
  author: cnreport
  version: "1.0"
---

# fd-cnreport-pdf-scripts-by-type-creator

Read **all** LLM rules for a given `document_type` from the rules database and
generate a **script rule per target indicator**.

## How to use

```bash
python .claude/skills/fd-cnreport-pdf-scripts-by-type-creator/scripts/generate_scripts_by_type.py \
  --document-type 年报/半年报/季报
```

- `--document-type` — the document_type to read (matches the `llm_rules`
  `document_type` column, originally from the CSV `report_type`).

The script reads every `llm_rules` row for that type, batches them, and asks the
LLM to produce one script rule per indicator (choosing `extract_rule` +
`position`). Results are validated and upserted into the `script_rules` table.

## Persistence

- **Rules database** (`script_rules` table) — runtime source of truth.
- **`scripts/fd-cnreport-pdf-scripts-by-type-creator.json`** — serialized copy.
