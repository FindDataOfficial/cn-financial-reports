---
name: fd-cnreport-pdf-llm-rules-creator
description: Generate LLM indicator rules for a whole PDF by splitting it into chapters via the parsed outline and producing rules per chapter. Validates with pydantic and persists to the rules database + this skill's scripts/ dir.
license: MIT
metadata:
  author: cnreport
  version: "1.0"
---

# fd-cnreport-pdf-llm-rules-creator

Generate **LLM indicator rules** for a whole PDF by splitting it into chapters
via the parsed outline and producing rules per chapter.

## How to use

```bash
python .claude/skills/fd-cnreport-pdf-llm-rules-creator/scripts/generate_pdf_llm_rules.py \
  --pdf path/to/report.pdf --document-type 年报
```

- `--pdf` — path (or URL) to the annual-report PDF.
- `--document-type` — report type tag (default `年报`).

The script fetches the PDF text + outline via `report_cache.get_or_fetch`,
slices the text into top-level chapters by the outline + page offsets, and
calls the LLM once per chapter to produce LLM rules. Each chapter's rules are
validated with pydantic and upserted into the `llm_rules` table; a serialized
copy is written to this skill's `scripts/` dir.

## Persistence

- **Rules database** (`llm_rules` table) — runtime source of truth.
- **`scripts/fd-cnreport-pdf-llm-rules-creator.json`** — serialized copy.

Invalid LLM output for a chapter is reported and skipped (does not abort the
whole PDF).
