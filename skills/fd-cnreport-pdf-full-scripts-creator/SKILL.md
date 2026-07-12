---
name: fd-cnreport-pdf-full-scripts-creator
description: Generate a full end-to-end extraction script for a document_type, drawing on the LLM and script rules in the rules database. Validates the output with pydantic and saves the runnable script to the skill's scripts/ dir.
license: MIT
metadata:
  author: cnreport
  version: "1.0"
---

# fd-cnreport-pdf-full-scripts-creator

Generate a **full end-to-end extraction script** for a given `document_type`,
drawing on the LLM and script rules in the rules database.

Unlike skills 1–4 (which produce rules), this skill produces a **runnable
Python script** that extracts every indicator of the given document_type in one
pass. The generated script reads rules from the rules database at runtime
(`rules_db.load_rules`) and dispatches each via the extraction pipeline, so it
stays correct as the DB rules evolve.

## How to use

```bash
python .claude/skills/fd-cnreport-pdf-full-scripts-creator/scripts/generate_full_scripts.py \
  --document-type 年报/半年报/季报
```

- `--document-type` — the document_type to generate a full extraction script for.

The script reads the `llm_rules` + `script_rules` for that type, asks the LLM
to emit a runnable extraction script, validates the output (script text +
covered indicators) with pydantic, and writes it to this skill's `scripts/` dir
as `full_extraction_<doctype>.py`.

## Persistence

- **`scripts/full_extraction_<doctype>.py`** — the runnable extraction script.
- **`scripts/fd-cnreport-pdf-full-scripts-creator.json`** — a manifest
  (document_type, covered indicators, script path).
