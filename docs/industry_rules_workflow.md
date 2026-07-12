# Industry Rules Workflow

This playbook defines how to add or maintain support for an industry-scoped
`document_type` using the existing generator skills and the coverage checker.

## 1. Choose the target taxonomy tuple

Pick:

- `industry` — Shenwan (申万) level-1 index code, e.g. `801780` (银行)
- `company_type`
- `report_kind`

Then compute the canonical `document_type`:

```bash
python scripts/list_industry_document_types.py --industry 801780
```

Example target:

- `cn/801780/listed/annual-report`

## 2. Prepare a representative input report

Use a representative PDF for the target `document_type`.

Examples:

- a listed bank annual report PDF (`801780`)
- a listed non-bank finance annual report PDF (`801790`)
- a listed machinery company annual report PDF (`801890`)

The PDF can be:

- a local file path
- a direct PDF URL

## 3. Generate LLM rules for the target `document_type`

Use the whole-PDF generator skill:

```bash
python .claude/skills/fd-cnreport-pdf-llm-rules-creator/scripts/generate_pdf_llm_rules.py \
  --pdf /path/to/report.pdf \
  --document-type cn/801780/listed/annual-report
```

What this does:

- parses the PDF outline
- splits the report into chapters
- generates chapter-level LLM rules
- validates them with pydantic
- upserts them into `llm_rules`
- writes a serialized copy to the skill `scripts/` directory

## 4. Derive script rules from LLM rules

After LLM rules exist for the target `document_type`, generate script rules:

```bash
python .claude/skills/fd-cnreport-pdf-scripts-by-type-creator/scripts/generate_scripts_by_type.py \
  --document-type cn/801780/listed/annual-report
```

What this does:

- reads all `llm_rules` rows for the chosen `document_type`
- chooses deterministic extractors per indicator
- validates the output
- upserts into `script_rules`
- writes a serialized copy to the skill `scripts/` directory

## 5. Check readiness against the declared baseline

Run the coverage gate:

```bash
python scripts/check_industry_coverage.py \
  --document-type cn/801780/listed/annual-report
```

Interpretation:

- `llm_ready = true` means every declared baseline indicator has an LLM rule
- `script_ready = true` means every declared baseline indicator has a script rule
- `supported = true` means both gates passed

## 6. Iterate when extraction quality fails

If extraction fails on a new report template:

1. identify the failed `document_type`
2. review the missing or weak indicators
3. regenerate or manually update the LLM rules for that `document_type`
4. regenerate script rules for that same `document_type`
5. rerun the coverage checker
6. rerun smoke tests on the representative corpus

## 7. Maintenance notes

- Keep `document_type` canonical: `cn/<sw_index_code>/<company_type>/<report_kind>`
- Keep baseline indicators in `docs/industry_indicator_baseline.json`
- Keep supported seed targets in `docs/industry_seed_support.json`
- Industry codes follow申万一级行业指数 (2021版), e.g. `801780` = 银行
- Do not mark an industry/document_type as supported until the coverage gate passes

