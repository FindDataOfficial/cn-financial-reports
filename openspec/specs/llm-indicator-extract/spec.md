# llm-indicator-extract Specification

## Purpose
TBD - created by syncing change test-llm-indicator-extract. Update Purpose after archive.
## Requirements

### Requirement: Supported periodic report forms
The LLM indicator extractor SHALL support exactly four periodic report forms: `年度报告`, `半年度报告`, `第一季度报告`, `第三季度报告`. Each form SHALL map to a compatibility key via `_FORM_COMPAT_KEY` (`年度报告→年报`, `半年度报告→半年报`, `第一季度报告→季报`, `第三季度报告→季报`) used to gate rule applicability. The four forms SHALL correspond to the four categories under the `定期报告` group in `cninfo_categories.json`.

#### Scenario: All four forms are accepted by the position-extraction entry point
- **WHEN** `extract_indicators_by_position(ticker_or_name=<synthetic>, year=<year>, extractor="llm", form=<form>)` is called for each of the four forms
- **THEN** the call does not raise `KeyError`/`ValueError` for any form, and the returned bundle's `form` field equals the requested form.

#### Scenario: Form-compat key mapping is exhaustive
- **WHEN** the test reads `_FORM_COMPAT_KEY` from `indicators_client`
- **THEN** its keys are exactly `{年度报告, 半年度报告, 第一季度报告, 第三季度报告}` and its values are exactly `{年报, 半年报, 季报, 季报}`.

#### Scenario: Forms match cninfo periodic-report categories
- **WHEN** the test reads `cninfo_categories.json` and selects the `定期报告` group
- **THEN** the group's category names are exactly the four supported forms.

### Requirement: LLM extraction is one call per section per module with a JSON records schema
For a set of `report`-type rules assigned to one section, the extractor SHALL make a single LLM call per module. The call SHALL send a system instruction requesting ONLY a JSON object matching the module's Pydantic model schema, and a user payload containing `period`, `wanted` (each entry carrying `indicator` and `unit`), and the section `text`. All `report`-type rules in a resolved section SHALL be included in the LLM call — there is no longer a split between `llm_rules` and `python_rules` within a section. The `extractor_mode: "python"` argument SHALL place all report rules in `unresolved` with note `skipped: llm extractor in python mode` (since no Python extractors exist).

#### Scenario: LLM receives the expected prompt shape
- **WHEN** the LLM extractor runs for a section with two report rules
- **THEN** the mocked `call_llm_json` is invoked exactly once for that section, its `user` argument parses as JSON containing `period`, `wanted` (length 2, each with `indicator` and `unit`), and `text`.

#### Scenario: Records are mapped back to rule names
- **WHEN** the LLM returns `{"records": [{"indicator": "资产总计", "value": 123, "unit": "元"}, {"indicator": "负债合计", "value": 45, "unit": "元"}]}`
- **THEN** the bundle's `indicators` map contains those two names with the returned values and `extractor: "llm"`.

#### Scenario: All report rules in a section go to LLM
- **WHEN** a section contains 5 `balance_sheet` rules and 3 `report_section` rules
- **THEN** the system makes 2 LLM calls (one per module), each including all rules of that module as fields in the Pydantic schema.

#### Scenario: Python mode skips all report rules
- **WHEN** `extractor_mode="python"` is passed and a `report` rule has `extractor: "llm"`
- **THEN** that rule is listed in `unresolved` with note `skipped: llm extractor in python mode` and no LLM call is made.

### Requirement: Missing indicators and errors resolve to null value
When an indicator is absent from the LLM response, the extractor SHALL record it with `value: null` and a note indicating it was not returned. When the LLM call raises (network, parse, or missing-API-key), the extractor SHALL NOT propagate the exception; it SHALL record every rule in that section with `value: null` and a note describing the failure class.

#### Scenario: Indicator not returned by the LLM
- **WHEN** the LLM returns records that omit a requested indicator
- **THEN** that indicator appears in `indicators` with `value: null` and a note containing "not returned".

#### Scenario: LLM call fails
- **WHEN** the mocked `call_llm_json` raises `RuntimeError`
- **THEN** every rule in the section appears in `indicators` with `value: null` and a note starting with `llm error`.

#### Scenario: API key not configured
- **WHEN** `LLM_API_KEY` is unset and the extractor runs
- **THEN** every rule in the section appears with `value: null` and note `LLM_API_KEY not configured`, and no HTTP call is attempted.

### Requirement: Form-incompatible rules are skipped, not extracted
Rules whose `report_type` does not include the requested form's compat key SHALL be placed in the `skipped` list with `source_type: "form_filter"` and note `not in <form>`, and SHALL NOT be sent to the LLM. Rules with no `report_type` SHALL be treated as compatible with every form.

#### Scenario: Annual-only rule is skipped for Q1
- **WHEN** extraction runs with `form="第一季度报告"` and a rule declares `report_type: "年报"`
- **THEN** that rule appears in `skipped` with `source_type: "form_filter"` and is not present in the `indicators` map and not in the `wanted` payload sent to the LLM.

#### Scenario: Rule without report_type is extracted for every form
- **WHEN** a rule has no `report_type` field and extraction runs for each of the four forms
- **THEN** the rule is delegated to the engine (not in `skipped`) for all four forms.

### Requirement: Result bundle mirrors the position-extraction script output
`extract_indicators_by_position(..., extractor="llm", form=<form>)` SHALL return a bundle with the header fields `{stock_code, company_name, year, form, pdf_url, cached, csv_path, extractor_mode}` and the lists `indicators`, `missing`, `unresolved`, `skipped`. Each `indicators` entry SHALL carry `{value, unit, source_type, extractor, source, period, provenance}`. The `skipped` array SHALL contain `{indicator, source_type, note}` entries. This shape SHALL match the bundle written to `./out/<stock>_<year>[_<form>].{json,csv}` by `scripts/extract_indicators_by_position.py`.

#### Scenario: Bundle shape on a successful LLM extraction
- **WHEN** extraction runs with the LLM mocked to return valid records
- **THEN** the returned bundle contains every header field, every `indicators` entry carries the seven fields, and `extractor_mode` equals the requested mode.

#### Scenario: Form is appended to the output stem for non-annual forms
- **WHEN** the script writes outputs for `form="半年度报告"`
- **THEN** the output stem is `<stock>_<year>_半年度报告` (not `<stock>_<year>`), matching the CLI's stem rule.

### Requirement: Tests run without network or API key
The LLM-extraction test suite SHALL make zero network calls and SHALL NOT require `LLM_API_KEY` or `OPENAI_API_KEY`. The suite SHALL mock `cnreport_tools.call_llm_json` and inject canned report text via the report-cache seam (or a documented fetch-function patch), consistent with the existing no-network contract in `test_cnreport.py`.

#### Scenario: Suite passes with no env and no network
- **WHEN** the new test module runs in an environment with `LLM_API_KEY` and `OPENAI_API_KEY` unset and no network access
- **THEN** every test passes and no `httpx` request leaves the process.
