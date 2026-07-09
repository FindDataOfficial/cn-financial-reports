# Indicators — source & process methodology

Generated from `indicator_rules.json`. Each indicator lists its source type, the concrete annual-report section selector chain (or akshare field / formula), the extractor, applicability, and a process note. `indicators.md` remains the human-authored catalog; this document is the machine-kept companion.

_Total rules: 321 · rules_hash: 922fdf82b7278503_

## balance_sheet

### 一、资产

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 资产总计 | akshare | akshare `balance_sheet.资产总计` | auto | * | 元 | Standard balance-sheet line item; akshare preferred. |
| 发放贷款及垫款 | report | report: 发放贷款及垫款 → 资产负债表 | llm | bank | 元 | Bank loan balance. |

### 二、负债

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 负债合计 | akshare | akshare `balance_sheet.负债合计` | auto | * | 元 | Standard balance-sheet line item. |
| 客户存款 | report | report: 客户存款 → 资产负债表 | llm | bank | 元 | Bank deposit balance; reported in the consolidated balance sheet narrative. |

### 三、所有者权益

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 所有者权益合计 | akshare | akshare `balance_sheet.所有者权益合计` | auto | * | 元 | Standard balance-sheet line item. |

### 四、核心指标

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 资本充足率 | report | report: 资本充足率分析* → 资本充足率 → 风险管理 | llm | bank | % | Bank-specific capital adequacy; not in akshare standard statements. Section title varies by bank. |
| 一级资本充足率 | report | report: 资本充足率分析* → 资本充足率 → 风险管理 | llm | bank | % | Tier-1 capital adequacy. |
| 核心一级资本充足率 | report | report: 资本充足率分析* → 资本充足率 → 风险管理 | llm | bank | % | Core tier-1 capital adequacy. |
| 风险加权资产合计 | report | report: 资本充足率 → 风险管理 | llm | bank | 元 | Risk-weighted assets. |
| 净利差 | report | report: 主要财务指标 → 财务概要 → 讨论与分析 → 管理层讨论与分析 | llm | bank | % | Net interest spread. |
| 净息差 | report | report: 主要财务指标 → 财务概要 → 讨论与分析 → 管理层讨论与分析 | llm | bank | % | Net interest margin. |
| 流动性覆盖率 | report | report: 流动性风险 → 风险管理 | llm | bank | % | Liquidity coverage ratio. |
| 流动性比例（人民币） | report | report: 流动性风险 → 风险管理 | llm | bank | % | RMB liquidity ratio. |

### 五、贷款质量

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 贷款和垫款总额 | report | report: 五、贷款质量* → 贷款质量 → 信用风险 → 风险管理 | llm | bank | 元 | Total loans & advances. |
| 不良贷款余额 | report | report: 贷款质量 → 信用风险 → 风险管理 | llm | bank | 元 | Non-performing loan balance. |
| 不良率 | computed | computed: `不良贷款余额 / 贷款和垫款总额 * 100` | computed | bank | % | Computed locally from extracted bases; not sent to the LLM. |
| 拨备覆盖率 | report | report: 贷款质量 → 信用风险 → 风险管理 | llm | bank | % | NPL coverage ratio. |
| 拨贷比 | report | report: 贷款质量 → 信用风险 | llm | bank | % | Provision-to-loan ratio. |
| 正常类贷款迁徙率 | report | report: 贷款质量 → 信用风险 | llm | bank | % | Pass-category migration rate. |
| 关注类贷款迁徙率 | report | report: 贷款质量 → 信用风险 | llm | bank | % | Special-mention migration rate. |
| 次级类贷款迁徙率 | report | report: 贷款质量 → 信用风险 | llm | bank | % | Substandard migration rate. |
| 可疑类贷款迁徙率 | report | report: 贷款质量 → 信用风险 | llm | bank | % | Doubtful migration rate. |
| 逾期贷款率 | report | report: 贷款质量 → 信用风险 | llm | bank | % | Overdue loan ratio. |
| 重组贷款率 | report | report: 贷款质量 → 信用风险 | llm | bank | % | Restructured loan ratio. |
| 逾期90天重组贷款率 | report | report: 贷款质量 → 信用风险 | llm | bank 国有大行/股份制 | % | Company-specific: only major banks disclose this breakdown. Sub-type scoped to 国有大行/股份制. |

### 六、员工情况

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 员工人数 | report | report: 人力资源管理 → 员工情况 → 员工 | python:headcount | * | 人 | Headcount; deterministic regex extractor (label + number on the same/next line). |

### 七、股本、股东以及估值

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 前十大股东持仓占总股本比例 | report | report: 股本变动 → 股份变动及股东情况 → 股东情况 → 主要股东 | llm | * | % | Top-10 shareholders' aggregate holding. |

### 资产负债表 — 一、资产

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 现金及存放中央银行款项 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 现金 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 存放中央银行款项 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 存放同业及其他金融机构款项 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 贵金属 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 拆出资金 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 买入返售金融资产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 衍生金融资产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 金融投资 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 以公允价值计量且其变动计入当期损益的金融投资 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 以摊余成本计量的金融投资 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 以公允价值计量且其变动计入其他综合收益的金融投资 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 以公允价值计量且其变动计入其他综合收益的债务工具投资 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 指定为以公允价值计量且其变动计入其他综合收益的权益工具投资 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 可供出售金融资产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 持有至到期投资 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 应收款项投资 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 应收利息 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 长期应收款 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 长期股权投资 | report | report: 资产负债表 | python:table_row | * | 股 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 投资性房地产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 在建工程 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 使用权资产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 无形资产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 商誉 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 递延所得税资产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |
| 其他资产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产) |

### 资产负债表 — 一、资产 / 附注

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 固定资产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 一、资产 / 附注) |

### 资产负债表 — 二、负债

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 向中央银行借款 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 同业存入及拆入 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 同业及其他金融机构存放款项 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 拆入资金 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 衍生金融负债 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 以公允价值计量且其变动计入当期损益的金融负债 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 卖出回购金融资产 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 应付职工薪酬 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 应交税费 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 合同负债 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 租赁负债 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 预计负债 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 应付利息 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 应付债券 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 递延所得税负债 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |
| 其他负债 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 二、负债) |

### 资产负债表 — 三、所有者权益

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 股本 | report | report: 资产负债表 | python:table_row | * | 股 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 其他权益工具 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 优先股 | report | report: 资产负债表 | python:table_row | * | 股 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 永续债 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 资本公积 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 减：库存股 | report | report: 资产负债表 | python:table_row | * | 股 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 其他综合收益 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 专项储备 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 盈余公积 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 一般风险准备金 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 未分配利润 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 外币报表折算差额 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 归属于母公司股东及其他权益持有者的权益合计 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 归属于母公司普通股股东权益合计 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |
| 少数股东权益 | report | report: 资产负债表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 资产负债表 — 三、所有者权益) |

## income_statement

### 一、营业收入

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 营业收入 | akshare | akshare `income_statement.营业收入` | auto | * | 元 | Standard income-statement line item. |
| 净利息收入 | akshare | akshare `income_statement.利息净收入` | auto | bank | 元 | Net interest income; akshare column name is 利息净收入. |
| 手续费及佣金净收入 | akshare | akshare `income_statement.手续费及佣金净收入` | auto | bank | 元 | Fee & commission net income. |

### 五、净利润

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 净利润 | akshare | akshare `income_statement.净利润` | auto | * | 元 | Standard income-statement line item. |

### 三、营业利润

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 营业利润 | akshare | akshare `income_statement.营业利润` | auto | * | 元 | Operating profit. |

### 四、利润总额

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 利润总额 | akshare | akshare `income_statement.利润总额` | auto | * | 元 | Total profit. |

### 六、每股收益

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 基本每股收益 | akshare | akshare `income_statement.基本每股收益` | auto | * | 元/股 | Basic EPS. |

### 九、分红、融资及涨跌幅

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 分红金额 | report | report: 利润分配 → 重要事项 | llm | * | 元 | Cash dividend amount. |

### 八、区域收入

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 境内收入 | report | report: 分部信息 → 分地区 → 营业收入构成 | llm | * | 元 | Domestic revenue; company-specific disclosure (not all companies report by region). |
| 境外收入 | report | report: 分部信息 → 分地区 → 营业收入构成 | llm | * | 元 | Overseas revenue; company-specific disclosure. |

### 利润表 — 一、营业收入

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 利息收入 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |
| 利息支出 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |
| 非息收入 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |
| 手续费及佣金收入 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |
| 手续费及佣金支出 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |
| 公允价值变动收益 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |
| 投资收益 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |
| 对联营企业及合营企业的投资收益 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |
| 汇兑收益 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |
| 其他业务收入 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 一、营业收入) |

### 利润表 — 二、营业支出

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 营业支出 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 二、营业支出) |
| 税金及附加 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 二、营业支出) |
| 业务及管理费用 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 二、营业支出) |
| 其他业务成本 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 二、营业支出) |
| 信用减值损失 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 二、营业支出) |
| 资产减值损失 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 二、营业支出) |
| 其他资产减值损失 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 二、营业支出) |

### 利润表 — 三、营业利润

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 加：营业外收入 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 三、营业利润) |
| 减：营业外支出 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 三、营业利润) |

### 利润表 — 四、利润总额

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 减：所得税费用 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 四、利润总额) |

### 利润表 — 五、净利润

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| （一）持续经营净利润 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 五、净利润) |
| （二）终止经营净利润 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 五、净利润) |
| 归属于母公司股东及其他权益持有者的净利润 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 五、净利润) |
| 归属于母公司普通股股东的净利润 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 五、净利润) |
| 少数股东损益 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 利润表 — 五、净利润) |

### 利润表 — 六、每股收益

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 稀释每股收益 | report | report: 利润表 | python:table_row | * | 股 | sourced from indicators_position.csv (section: 利润表 — 六、每股收益) |

### 综合收益表

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 综合收益总额 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 综合收益表) |
| 归属于母公司股东及其他权益持有者的综合收益总额 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 综合收益表) |
| 归属于母公司普通股股东的综合收益总额 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 综合收益表) |
| 归属于少数股东的综合收益总额 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 综合收益表) |
| 其他综合收益的税后净额 | report | report: 利润表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 综合收益表) |

## cashflow

### 一、经营活动产生的现金流量

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 经营活动产生的现金流量净额 | akshare | akshare `cashflow.经营活动产生的现金流量净额` | auto | * | 元 | Operating cash flow net. |

### 二、投资活动产生的现金流量

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 投资活动产生的现金流量净额 | akshare | akshare `cashflow.投资活动产生的现金流量净额` | auto | * | 元 | Investing cash flow net. |

### 三、筹资活动产生的现金流量

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 筹资活动产生的现金流量净额 | akshare | akshare `cashflow.筹资活动产生的现金流量净额` | auto | * | 元 | Financing cash flow net. |

### 现金流量表 — 经营活动

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 发放贷款及垫款的净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 向中央银行借款净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 客户存款和同业及其他金融机构存放款项净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 客户存款净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 同业及其他金融机构存放款项净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 存放中央银行和同业及其他金融机构款项净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 存放中央银行款项净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 存放同业及其他金融机构款项净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 拆入资金及卖出回购金融资产净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 拆入资金净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 卖出回购业务资金净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 拆出资金及买入返售金融资产净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 拆出资金净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 买入返售金融资产款净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 为交易目的而持有的金融资产净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 收取利息、手续费及佣金的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 收到的其他与经营活动有关现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 经营活动现金流入小计 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 发放贷款及垫款的净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 向中央银行借款净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 客户存款和同业及其他金融机构存放款项净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 客户存款净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 同业及其他金融机构存放款项净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 存放中央银行和同业及其他金融机构款项净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 存放中央银行款净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 存放同业及其他金融机构款项净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 拆入资金及卖出回购金融资产款净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 拆入资金净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 卖出回购业务资金净减少额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 拆出资金及买入返售金融资产净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 拆出资金增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 买入返售金融资产净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 为交易目的而持有的金融资产净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 支付利息、手续费及佣金的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 支付给职工及为职工支付的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 支付的各种税费 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 支付的其他与经营活动有关现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |
| 经营活动现金流出小计 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 经营活动) |

### 现金流量表 — 投资活动

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 收回投资收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 取得投资收益所收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 处置固定资产、无形资产及其他长期资产收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 处置子公司、合营联营企业及其他营业单位收到的现金净额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 处置子公司或其他营业单位收到的现金净额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 处置合营或联营公司所收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 收到的其他与投资活动相关的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 投资活动现金流入小计 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 投资所支付的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 购建固定资产、无形资产及其他长期资产所支付的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 取得子公司、合营联营企业及其他营业单位支付的现金净额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 取得子公司及其营业单位支付的现金净额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 取得联营及合营公司支付的现金净额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 支付的其他与投资活动有关的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |
| 投资活动现金流出小计 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 投资活动) |

### 现金流量表 — 筹资活动

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 吸收投资收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 子公司吸收少数股东投资收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 资产证券化收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 发行存款证收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 发行债券收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 发行同业存单收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 发行永续债收到的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 上市募集资金总额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 收到的其他与筹资活动有关的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 筹资活动产生的现金流入小计 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 偿还已发行存款证支付的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 偿付债务支付的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 偿还已发行同业存单支付的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 偿还债券利息支付的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 分配股利、利润或偿付利息所支付的现金 | report | report: 现金流量表 | python:table_row | * | 股 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 子公司支付少数股东股利及利润 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 赎回非控制性权益支付的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 支付新股发行费用 | report | report: 现金流量表 | python:table_row | * | 股 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 支付的其他与筹资活动有关的现金 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |
| 筹资活动产生的现金流出小计 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 筹资活动) |

### 现金流量表 — 现金及现金等价物净增加额

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 汇率变动对现金及现金等价物的影响 | report | report: 现金流量表 | python:percent_value | * | % | sourced from indicators_position.csv (section: 现金流量表 — 现金及现金等价物净增加额) |
| 期初现金及现金等价物的余额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 现金及现金等价物净增加额) |
| 现金及现金等价物的净增加额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 现金及现金等价物净增加额) |
| 期末现金及现金等价物净余额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 现金及现金等价物净增加额) |

### 现金流量表 — 附注

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 加：资产减值准备 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 固定资产折旧、油气资产折耗、生产性生物资产折旧 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 投资性房地产的折旧及摊销 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 使用权资产摊销 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 无形资产摊销 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 长期待摊费用摊销 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 处置固定资产、无形资产和其他长期资产的损失 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 固定资产报废损失 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 公允价值变动损失 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 财务费用 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 投资损失 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 递延所得税资产减少 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 递延所得税负债增加 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 存货的减少 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 经营性应收项目的减少 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 经营性应付项目的增加 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 其他 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 一年内到期的可转换公司债券 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |
| 融资租入固定资产 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表 — 附注) |

### 现金流量表

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 经投融产生的现金流量净额 | report | report: 现金流量表 | python:table_row | * | 元 | sourced from indicators_position.csv (section: 现金流量表) |

## financial_ratio

### 七、偿债及资本结构

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 资产负债率 | computed | computed: `负债合计 / 资产总计 * 100` | computed | * | % | Computed locally. |

### 四、盈利能力

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 净利润率 | computed | computed: `净利润 / 营业收入 * 100` | computed | * | % | Computed locally. |
| 营业利润率 | computed | computed: `营业利润 / 营业收入 * 100` | computed | * | % | Computed locally. |
| 拨贷比_coverage | computed | computed: `贷款损失准备 / 不良贷款余额 * 100` | computed | bank | % | Computed coverage ratio example; requires 贷款损失准备 to be extracted first. |

### 一、人均指标

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 人均营业收入 | computed | computed: `营业收入 / 员工人数` | computed | * | 元/人 | Computed locally; requires 员工人数 from the report path. |
| 人均净利润 | computed | computed: `净利润 / 员工人数` | computed | * | 元/人 | Computed locally. |

## report_section

### 财务报表附注

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 固定资产占总资产比率 | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 商誉占净资产比率 | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 股东权益占比 | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 归属于母公司普通股股东的每股股东权益 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 净息收入占比 | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 非息收入占比 | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 收入成本比 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 有效税率 | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 归属于母公司普通股股东的扣除非经常性损益的净利润 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 扣非净利润占比 | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 归属于母公司普通股股东的加权ROE | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 归属于母公司普通股股东的扣非加权ROE | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 贷存比 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 归属于母公司普通股股东的每股收益 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 归属于母公司普通股股东的每股扣非收益 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 每股资本公积 | report | report: 财务报表附注 | llm | * | 股 | sourced from indicators_position.csv (section: 财务报表附注) |
| 每股未分配利润 | report | report: 财务报表附注 | llm | * | 股 | sourced from indicators_position.csv (section: 财务报表附注) |
| 每股分红 | report | report: 财务报表附注 | llm | * | 股 | sourced from indicators_position.csv (section: 财务报表附注) |
| 每股经营活动产生的现金流量 | report | report: 财务报表附注 | llm | * | 股 | sourced from indicators_position.csv (section: 财务报表附注) |
| 每股经营活动产生的现金流量净额 | report | report: 财务报表附注 | llm | * | 股 | sourced from indicators_position.csv (section: 财务报表附注) |
| 归属于少数股股东的ROE | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 归属于母公司普通股股东的ROE | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 归属于母公司普通股股东的扣非ROE | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 风险加权资产收益率（RORWA） | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 净资产收益率（ROE） | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 杠杆倍数 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 总资产收益率（ROA） | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 总资产周转率 | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 固定资产周转率 | report | report: 财务报表附注 | python:percent_value | * | % | sourced from indicators_position.csv (section: 财务报表附注) |
| 固定资产周转天数 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 股东权益周转天数 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 总资产周转天数 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |
| 自由现金流量 | report | report: 财务报表附注 | llm | * | 元 | sourced from indicators_position.csv (section: 财务报表附注) |

### 风险管理 — 流动性风险

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 流动性比例（外币） | report | report: 风险管理 — 流动性风险 | python:percent_value | * | % | sourced from indicators_position.csv (section: 风险管理 — 流动性风险) |
| 流动性比例（折人民币） | report | report: 风险管理 — 流动性风险 | python:percent_value | * | % | sourced from indicators_position.csv (section: 风险管理 — 流动性风险) |

### 风险管理 — 信用风险 — 贷款质量

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 正常类贷款 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 关注类贷款 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 次级类贷款 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 可疑类贷款 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 损失类贷款 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 逾期贷款 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 逾期90天贷款 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 重组贷款 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 逾期90天的重组贷款 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 贷款损失准备 | report | report: 风险管理 — 信用风险 — 贷款质量 | llm | * | 元 | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 不良贷款拨备覆盖率 | report | report: 风险管理 — 信用风险 — 贷款质量 | python:percent_value | * | % | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |
| 逾期90天贷款率 | report | report: 风险管理 — 信用风险 — 贷款质量 | python:percent_value | * | % | sourced from indicators_position.csv (section: 风险管理 — 信用风险 — 贷款质量) |

### 人力资源管理 — 员工情况

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 博士人数 | report | report: 人力资源管理 — 员工情况 | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况) |
| 硕士人数 | report | report: 人力资源管理 — 员工情况 | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况) |
| 学士人数 | report | report: 人力资源管理 — 员工情况 | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况) |
| 大专人数 | report | report: 人力资源管理 — 员工情况 | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况) |
| 高中及以下人数 | report | report: 人力资源管理 — 员工情况 | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况) |
| 人均薪酬 | report | report: 人力资源管理 — 员工情况 | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况) |

### 人力资源管理 — 员工情况（按职能）

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 生产人员人数 | report | report: 人力资源管理 — 员工情况（按职能） | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况（按职能）) |
| 销售人员人数 | report | report: 人力资源管理 — 员工情况（按职能） | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况（按职能）) |
| 技术人员人数 | report | report: 人力资源管理 — 员工情况（按职能） | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况（按职能）) |
| 财务人员人数 | report | report: 人力资源管理 — 员工情况（按职能） | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况（按职能）) |
| 行政人员人数 | report | report: 人力资源管理 — 员工情况（按职能） | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况（按职能）) |
| 其他人员人数 | report | report: 人力资源管理 — 员工情况（按职能） | python:headcount | * | 人 | sourced from indicators_position.csv (section: 人力资源管理 — 员工情况（按职能）) |

### 股本变动 — 股东情况

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 总股数 | report | report: 股本变动 — 股东情况 | llm | * | 股 | sourced from indicators_position.csv (section: 股本变动 — 股东情况) |
| 流通股数 | report | report: 股本变动 — 股东情况 | llm | * | 股 | sourced from indicators_position.csv (section: 股本变动 — 股东情况) |

### 股东情况

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 总股东人数（季度） | report | report: 股东情况 | python:headcount | * | 人 | sourced from indicators_position.csv (section: 股东情况) |
| A股股东人数（季度） | report | report: 股东情况 | python:headcount | * | 人 | sourced from indicators_position.csv (section: 股东情况) |

### 股东情况 — 主要股东

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 第一大股东持仓占总股本比例 | report | report: 股东情况 — 主要股东 | python:percent_value | * | % | sourced from indicators_position.csv (section: 股东情况 — 主要股东) |
| 前十大流通股东持仓占流通股本比例 | report | report: 股东情况 — 主要股东 | python:percent_value | * | % | sourced from indicators_position.csv (section: 股东情况 — 主要股东) |

### 分部信息 — 分地区

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 境内营业成本 | report | report: 分部信息 — 分地区 | llm | * | 元 | sourced from indicators_position.csv (section: 分部信息 — 分地区) |
| 境内毛利率 | report | report: 分部信息 — 分地区 | python:percent_value | * | % | sourced from indicators_position.csv (section: 分部信息 — 分地区) |
| 境内收入占比 | report | report: 分部信息 — 分地区 | python:percent_value | * | % | sourced from indicators_position.csv (section: 分部信息 — 分地区) |
| 境外营业成本 | report | report: 分部信息 — 分地区 | llm | * | 元 | sourced from indicators_position.csv (section: 分部信息 — 分地区) |
| 境外毛利率 | report | report: 分部信息 — 分地区 | python:percent_value | * | % | sourced from indicators_position.csv (section: 分部信息 — 分地区) |
| 境外收入占比 | report | report: 分部信息 — 分地区 | python:percent_value | * | % | sourced from indicators_position.csv (section: 分部信息 — 分地区) |

### 重要事项 — 利润分配

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 分红率 | report | report: 重要事项 — 利润分配 | python:percent_value | * | % | sourced from indicators_position.csv (section: 重要事项 — 利润分配) |
| A股分红金额 | report | report: 重要事项 — 利润分配 | llm | * | 股 | sourced from indicators_position.csv (section: 重要事项 — 利润分配) |

### 融资情况

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| A股融资金额 | report | report: 融资情况 | llm | * | 股 | sourced from indicators_position.csv (section: 融资情况) |

### 客户情况

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 前五大客户收入占比 | report | report: 客户情况 | python:percent_value | * | % | sourced from indicators_position.csv (section: 客户情况) |

### 供应商情况

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 前五大供应商采购占比 | report | report: 供应商情况 | python:percent_value | * | % | sourced from indicators_position.csv (section: 供应商情况) |

## market_data

### 市场数据（外部）

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 市值 | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 市场数据（外部）) |
| PE-TTM | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 市场数据（外部）) |
| PE-TTM（扣非） | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 市场数据（外部）) |
| PB | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 市场数据（外部）) |
| PB（不含商誉） | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 市场数据（外部）) |
| PS-TTM | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 市场数据（外部）) |
| PCF-TTM | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 市场数据（外部）) |
| 股息率 | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 市场数据（外部）) |
| 年度涨跌幅 | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 市场数据（外部）) |

### 基金持仓（外部）

| Indicator | source_type | source | extractor | applies_to | unit | note |
|---|---|---|---|---|---|---|
| 进公募基金前十大持仓占流通股本比例 | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 基金持仓（外部）) |
| 公募基金持仓占流通股本比例 | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 基金持仓（外部）) |
| 公募基金+自由流通股东持仓占自由流通股本比例 | external | external (realtime/market — not in report PDF) |  | * |  | sourced from indicators_position.csv (section: 基金持仓（外部）) |

## Adding a new rule

Append an entry to `indicator_rules.json`. Required fields: `name`, `module`, `subgroup`, `applies_to`, `source_type`, and the matching `source` spec (`{statement, field}` for akshare, `{selectors:[...], extractor}` for report, `{formula, inputs}` for computed). Optional: `aliases`, `unit`, `period_type`, `direction`, `note`. No Python change is needed — `list_indicators`, `get_indicator`, `extract_indicators`, and the script all read the JSON at call time. Then re-run `python indicators_client.py --render-methodology > docs/indicators-methodology.md` to refresh this document.

## Adding a new extractor

1. Write a function `(section_text, rule, period) -> {value, unit, note}` in `indicators_extractors.py`.
2. Call `register('your_name', your_fn)` at import time.
3. Set `"extractor": "python:your_name"` on the rule(s) that should use it.

The engine dispatches by name; no engine change is required. Python extractors receive the already-sliced, cache-backed section text and never touch the PDF themselves. Use `--extractor python` on the script to run LLM-free where possible.

## LLM section cache

The LLM extractor persists the raw `{records:[...]}` response to `<CNREPORT_CACHE_DIR>/llm_sections/<key>.json`, keyed by `(pdf_url, section_key, period, rules_hash)`. After a section has been extracted once, subsequent runs — including single-indicator lookups via `get_indicator` and re-runs with different indicator subsets — reuse the cached records and only re-query the LLM for indicators not yet cached.

The bundle exposes a `section_cache_reuse: <int>` field that counts records served from the section cache in that run (distinct from `cached: true`, which indicates a full bundle hit). The cache is on by default; set `LLM_SECTION_CACHE=off` to disable it at runtime. CNINFO reports are immutable, so the cache is safe to leave on indefinitely.

## Concurrency

`extract_indicators` runs its per-section LLM calls and `akshare` calls concurrently up to a worker cap (sections are independent: disjoint indicator names, distinct section-cache keys), so a cold first pass takes `~1 × LLM_latency` instead of `N_sections × latency`. The cap is set by the `concurrency` parameter, falling back to the `EXTRACT_CONCURRENCY` env var (default `4`); `concurrency=1` runs inline with no thread pool and reproduces the prior sequential behavior and call order exactly. The bundle reports the cap used via a `concurrency: <int>` field.

`extract_indicators_batch(targets, ...)` runs many `(ticker, year[, form])` extractions concurrently (powering `scripts/extract_indicators_by_position.py --from-file` and `scripts/extract_indicators_multiyear.py`). Its batch cap (`concurrency`, default `EXTRACT_BATCH_CONCURRENCY`/`2`) is independent of the in-call cap (`extract_concurrency`, default `EXTRACT_CONCURRENCY`/`4`), so peak in-flight LLM calls is bounded by their product (`2 × 4 = 8` by default). Lower either if the provider rate-limits; set either to `1` for strictly sequential runs. The thread pool relies on the existing concurrency boundaries — `call_llm_json` issues a fresh `httpx.post` per call, `report_cache`/`llm_section_cache` write atomically to distinct keys, and `_RULES_CACHE` is read-only after first load — so no new locking is needed.

