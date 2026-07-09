---
name: fd-cnreport-llm-rules-creator
description: Generate LLM indicator rules from a piece/section of a Chinese financial document. Reads a section excerpt, asks the LLM to produce rules (indicator, instruction, position, document_type), validates them with pydantic, and persists to the rules database + this skill's scripts/ dir.
license: MIT
metadata:
  author: cnreport
  version: "1.0"
---

# fd-cnreport-llm-rules-creator

Generate **LLM indicator rules** from a piece (section excerpt) of a Chinese
financial report.

## What it produces

For each indicator found in the excerpt, an LLM rule with the demand's fields:

- `indicator` — the indicator name (Chinese)
- `instruction` — how the LLM should extract the value
- `position` — the section/selector the value lives in
- `document_type` — e.g. `年报`

…plus shared metadata (`module`, `applies_to`, `unit`, `period_type`).

## How to use

Run the generator script from the repo root:

```bash
python .claude/skills/fd-cnreport-llm-rules-creator/scripts/generate_llm_rules.py \
  --text path/to/section_excerpt.txt \
  --document-type 年报
```

- `--text` — path to a UTF-8 text file containing the document section excerpt.
- `--document-type` — the report type to tag rules with (default `年报`).

The script calls the LLM (`LLM_*` env), validates the response with a pydantic
model, upserts each rule into the `llm_rules` table (rules database), and writes
a serialized copy to this skill's `scripts/` directory.

## Persistence

- **Rules database** (`llm_rules` table, via `rules_db.upsert_llm_rule`) — the
  runtime source of truth.
- **`scripts/fd-cnreport-llm-rules-creator.json`** — a serialized copy for
  inspection / version control.

Invalid LLM output is rejected (pydantic validation raises); nothing is written.
