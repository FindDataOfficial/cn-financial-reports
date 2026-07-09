## MODIFIED Requirements

### Requirement: LLM extraction is one call per section with a JSON records schema
For a set of `report`-type rules assigned to one section, the extractor SHALL make a single LLM call **or reuse a cached response from the section cache** (`llm_section_cache`). The call SHALL send a system instruction requesting ONLY a JSON object with a `records` array (one record per requested indicator) and a user payload containing `period`, `wanted` (each entry carrying `indicator` and `unit`), and the section `text`. The expected response SHALL be parseable as `{"records": [{"indicator": <str>, "value": <number|string|null>, "period": <str>, "unit": <str>}, ...]}`. The cache key SHALL depend on `(pdf_url, section_key, period, wanted_signature, rules_hash)` so that identical queries on the same PDF reuse the cached records, and any change in section text, wanted set, or rule set triggers a fresh LLM call.

#### Scenario: LLM receives the expected prompt shape
- **WHEN** the LLM extractor runs for a section with two report rules and no section-cache hit
- **THEN** the mocked `call_llm_json` is invoked exactly once for that section, its `user` argument parses as JSON containing `period`, `wanted` (length 2, each with `indicator` and `unit`), and `text`.

#### Scenario: Records are mapped back to rule names
- **WHEN** the LLM returns `{"records": [{"indicator": "资产总计", "value": 123, "unit": "元"}, {"indicator": "负债合计", "value": 45, "unit": "元"}]}`
- **THEN** the bundle's `indicators` map contains those two names with the returned values and `extractor: "llm"`.

#### Scenario: Section cache hit avoids a second LLM call
- **WHEN** a previous run cached a response for `(pdf_url, section_key, period, wanted_signature, rules_hash)` and the current run requests the same section with the same wanted set and the same `rules_hash`
- **THEN** the cached records are returned without invoking `call_llm_json`.

#### Scenario: Subset reuse merges cached and fresh records
- **WHEN** the section cache holds records for `{A, B}` and the current run requests `{A, B, C}`
- **THEN** `call_llm_json` is invoked once with `wanted = [C]`, the returned `C` is merged with the cached `A`, `B`, and the merged set is written to the cache under the new wanted signature.

### Requirement: Result bundle mirrors the position-extraction script output
`extract_indicators_by_position(..., extractor="llm", form=<form>)` SHALL return a bundle with the header fields `{stock_code, company_name, year, form, pdf_url, cached, csv_path, extractor_mode, section_cache_reuse}` and the lists `indicators`, `missing`, `unresolved`, `skipped`. Each `indicators` entry SHALL carry `{value, unit, source_type, extractor, source, period, provenance}`. The `skipped` array SHALL contain `{indicator, source_type, note}` entries. The `section_cache_reuse` field SHALL be an integer count of indicator records served from the section cache (zero when no section cache hit occurred); it is independent of `cached`, which indicates a full bundle hit.

#### Scenario: Bundle shape on a successful LLM extraction
- **WHEN** extraction runs with the LLM mocked to return valid records
- **THEN** the returned bundle contains every header field, every `indicators` entry carries the seven fields, `extractor_mode` equals the requested mode, and `section_cache_reuse` is an integer.

#### Scenario: Form is appended to the output stem for non-annual forms
- **WHEN** the script writes outputs for `form="半年度报告"`
- **THEN** the output stem is `<stock>_<year>_半年度报告` (not `<stock>_<year>`), matching the CLI's stem rule.

#### Scenario: section_cache_reuse reflects cached records
- **WHEN** a run reuses N indicator records from the section cache
- **THEN** `bundle["section_cache_reuse"]` equals N.
