# Indicators coverage — implemented rule set

Summary of `indicator_rules.json` (the implemented rule set). Banking rules are hand-authored; the broader set is migrated from `docs/indicators_position.csv` by `scripts/migrate_indicators_csv.py`. Per-rule source/process detail lives in `docs/indicators-methodology.md`.

## Summary

- Total rules: **321**
- **Fetchable** (report / akshare / computed): **309**
- **External** (realtime/market — not in report PDF, listed in `skipped`): **12**
- rules_hash: `922fdf82b7278503`

## By source_type

| source_type | count | meaning |
|---|---|---|
| akshare | 13 | read from akshare structured statements |
| report | 289 | extracted from the annual-report PDF section |
| computed | 7 | derived locally from base values via a formula |
| external | 12 | realtime/market data — not in the report PDF |

## By module

| module | rules |
|---|---|
| balance_sheet | 86 |
| cashflow | 100 |
| financial_ratio | 6 |
| income_statement | 41 |
| market_data | 12 |
| report_section | 76 |

## Refresh

Regenerate after editing the CSV / rules:

```
python scripts/migrate_indicators_csv.py          # sync CSV → indicator_rules.json
python indicators_client.py --render-methodology > docs/indicators-methodology.md
python indicators_client.py --render-coverage > docs/indicators-coverage.md
```

