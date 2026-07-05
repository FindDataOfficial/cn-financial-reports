# 工商银行 2023 年度报告 — indicator locations

Source: **工商银行2023年度报告**  (published 2024-03-27)  
PDF: http://static.cninfo.com.cn/finalpage/2024-03-28/1219429144.PDF  
Resolved company: 工商银行 (601398)  
PDF cached: True; outline entries parsed: 339

Every `report`-type indicator rule was resolved against this report's 目录; all 26 locate a section. The 工行 annual report uses `1. 释义 / 2. … / 5. 财务概要 / 7. 讨论与分析 / 7.4 风险管理 / 7.5 资本管理 / 8. 股本变动及主要股东持股情况 / 10. 公司治理报告 / 14. 重要事项 / 16. 审计报告及财务报告 (附注四/五/七)` numbering.

## Report-type indicators → located section

| Indicator | matched selector | actual TOC title |
|---|---|---|
| 客户存款 | `客户存款` | 19. 客户存款 |
| 发放贷款及垫款 | `资产负债表` | 7. 2.2 资产负债表项目分析 |
| 资本充足率 | `资本充足率` | 7. 5.1 资本充足率及杠杆率情况 |
| 一级资本充足率 | `资本充足率` | 7. 5.1 资本充足率及杠杆率情况 |
| 核心一级资本充足率 | `资本充足率` | 7. 5.1 资本充足率及杠杆率情况 |
| 风险加权资产合计 | `资本充足率` | 7. 5.1 资本充足率及杠杆率情况 |
| 净利差 | `财务概要` | 5. 财务概要 |
| 净息差 | `财务概要` | 5. 财务概要 |
| 流动性覆盖率 | `流动性风险` | 7. 4.5 流动性风险 |
| 流动性比例（人民币） | `流动性风险` | 7. 4.5 流动性风险 |
| 贷款和垫款总额 | `信用风险` | 7. 4.2 信用风险 |
| 不良贷款余额 | `信用风险` | 7. 4.2 信用风险 |
| 拨备覆盖率 | `信用风险` | 7. 4.2 信用风险 |
| 拨贷比 | `信用风险` | 7. 4.2 信用风险 |
| 正常类贷款迁徙率 | `信用风险` | 7. 4.2 信用风险 |
| 关注类贷款迁徙率 | `信用风险` | 7. 4.2 信用风险 |
| 次级类贷款迁徙率 | `信用风险` | 7. 4.2 信用风险 |
| 可疑类贷款迁徙率 | `信用风险` | 7. 4.2 信用风险 |
| 逾期贷款率 | `信用风险` | 7. 4.2 信用风险 |
| 重组贷款率 | `信用风险` | 7. 4.2 信用风险 |
| 逾期90天重组贷款率 | `信用风险` | 7. 4.2 信用风险 |
| 员工人数 | `人力资源管理` | 7. 3.8 人力资源管理与员工机构情况 |
| 前十大股东持仓占总股本比例 | `股本变动` | 8. 股本变动及主要股东持股情况 |
| 分红金额 | `重要事项` | 14. 重要事项 |
| 境内收入 | `分部信息` | 五、 分部信息 |
| 境外收入 | `分部信息` | 五、 分部信息 |

## Validated end-to-end (no LLM key needed)

| Indicator | route | value | source |
|---|---|---|---|
| 营业收入 | akshare | 838270000000.0 | akshare:income_statement.营业收入 |
| 净利润 | akshare | 370766000000.0 | akshare:income_statement.净利润 |
| 资产总计 | akshare | 53477772999999.99 | akshare:balance_sheet.资产总计 |
| 员工人数 | python:headcount | 419252.0 | report:人力资源管理 |

## Findings

- **All 26 `report`-type indicators locate a section** in 工行's 2023 TOC (was 21/26; fixed 5 selectors against the real TOC).
- **akshare route validated**: 营业收入=838,270,000,000 (¥8,382.70亿), 净利润=370,766,000,000 (¥3,707.66亿) — both match the report.
- **akshare `资产总计` discrepancy**: akshare returned 53,477,772,999,999.99 but the report's 资产总计 = **44,697,079** (¥44.70万亿, in 百万元). The PDF figure is authoritative; the akshare value picked the wrong row/column. Recommend cross-checking akshare-sourced balance-sheet totals against the PDF, or switching 资产总计 to a `report` rule on `合并资产负债表`.
- **python extractor validated**: 员工人数=419,252 人 via the new `headcount` extractor on the `人力资源管理` section.
- **LLM-extractor route**: 21 indicators (资本充足率 family, 贷款质量 family, 净利差/净息差, 前十大股东, 境内/境外收入, 分红金额, etc.) are section-located and ready; extraction requires `LLM_API_KEY` to run `ai_extract`.
- **Sections 工行 uses** (vs the generic selectors): 资本充足率 → `7.5.1 资本充足率及杠杆率情况`; 贷款质量 → `7.4.2 信用风险`; 流动性 → `7.4.5 流动性风险`; 净息差/净利差 → `5. 财务概要`; 前十大股东 → `8. 股本变动及主要股东持股情况`; 员工 → `7.3.8 人力资源管理与员工机构情况`; 境内/境外收入 → `五、 分部信息` (附注).