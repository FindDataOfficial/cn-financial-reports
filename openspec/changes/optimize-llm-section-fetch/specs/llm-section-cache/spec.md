## ADDED Requirements

### Requirement: Persistent section-level LLM response cache
The system SHALL persist the raw `{records: [...]}` response returned by `call_llm_json` to a section-level cache. The cache SHALL be keyed by a stable hash of `(pdf_url, section_key, period, wanted_signature, rules_hash)` and SHALL live on disk under the same directory used by `report_cache`. Cache lookups SHALL occur before any HTTP call to the LLM, and cache writes SHALL be atomic (write to a temp file, then `os.replace`). The cache SHALL be opt-out via an environment variable (`LLM_SECTION_CACHE=off`); the default SHALL be enabled.

#### Scenario: Cache hit avoids LLM call
- **WHEN** the same section (same `pdf_url`, `section_key`, `period`, `wanted_signature`, `rules_hash`) is queried twice across two `extract_indicators_by_position` runs
- **THEN** the second run makes zero calls to `call_llm_json` and returns the same indicator values as the first run.

#### Scenario: Cache miss triggers exactly one LLM call
- **WHEN** the section is queried for the first time
- **THEN** exactly one call to `call_llm_json` is made and the response is persisted to the cache.

#### Scenario: Cache key depends on section text and wanted set
- **WHEN** the section text is changed (different `pdf_url` or different `section_key`) or the wanted indicator set is changed
- **THEN** the previous cache entry is not reused and a fresh LLM call is made.

#### Scenario: Cache write failure does not break extraction
- **WHEN** the cache directory is not writable
- **THEN** the extractor returns the LLM response (or null on error) as if the cache were absent, and the failure is logged at debug level.

#### Scenario: Cache is disabled via env var
- **WHEN** `LLM_SECTION_CACHE=off` is set
- **THEN** no cache files are read or written and the extractor behaves identically to the pre-cache implementation.

### Requirement: Subset reuse during a single extraction
When `extract_indicators` processes a section whose wanted indicators partially overlap a cached response, the engine SHALL reuse the cached records for the overlapping subset and SHALL call the LLM only for the missing subset. The merged result SHALL be returned and SHALL be written back to the cache under the new wanted signature.

#### Scenario: Overlapping wanted sets reuse cached records
- **WHEN** a previous run cached `{A, B, C}` for section X and the current run requests `{A, B, D}`
- **THEN** the LLM is called once with `wanted = [D]`, the cache is updated to `{A, B, C, D}` (or a new entry under the new wanted signature), and the returned values for `A` and `B` match the cached values.

#### Scenario: Bundle reports partial cache reuse
- **WHEN** at least one section reuses cached records during an `extract_indicators` run
- **THEN** the returned bundle contains `section_cache_reuse: <int>` set to the number of indicator records served from the section cache (distinct from `cached: true` which indicates a full bundle hit).

### Requirement: Single-indicator resolution reuses the section cache
When `get_indicator` is called for a `report`-source rule, the engine SHALL consult the section cache before invoking `_llm_extract_section`. A cache hit SHALL return the cached value with `extractor: "llm"` and a `note` indicating the value came from the section cache.

#### Scenario: get_indicator for a previously-extracted rule does not call LLM
- **WHEN** `get_indicator("资产总计", "601398", 2023)` is called after `extract_indicators_by_position("601398", 2023)` has already extracted that rule from the same PDF
- **THEN** the call to `call_llm_json` is not made and the returned value matches the bundle.

#### Scenario: get_indicator for a not-yet-cached rule falls through to LLM
- **WHEN** `get_indicator` is called for a rule that has no entry in the section cache
- **THEN** `_llm_extract_section` is called with the section's text and the single rule, the response is cached, and the value is returned.

### Requirement: Cache invalidation on rule-set change
The cache SHALL be invalidated when the rule set's `rules_hash` changes (i.e. when `indicator_rules.json` is edited). The invalidation SHALL be implemented by including `rules_hash` in the cache key, so a new hash produces a fresh cache namespace. Old cache files MAY remain on disk; they are not read under the new namespace and are not auto-pruned by this requirement.

#### Scenario: Rule-set edit invalidates the cache
- **WHEN** `indicator_rules.json` is edited so `rules_hash()` returns a new value
- **THEN** the next extraction run does not reuse cache entries written under the previous hash and makes a fresh LLM call.

### Requirement: No-network / no-key test contract preserved
The section cache SHALL NOT introduce a hard dependency on `LLM_API_KEY` at import time. The cache SHALL be bypassable in tests by setting `LLM_SECTION_CACHE=off` in the test fixture, mirroring the existing no-network contract.

#### Scenario: Test suite passes with no LLM key and cache disabled
- **WHEN** the test module runs with `LLM_API_KEY` and `OPENAI_API_KEY` unset and `LLM_SECTION_CACHE=off`
- **THEN** every test passes and no `httpx` request leaves the process.
