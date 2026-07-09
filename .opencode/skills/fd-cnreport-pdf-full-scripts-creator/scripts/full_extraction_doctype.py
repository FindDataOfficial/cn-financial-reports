import rules_db
import indicators_client

def main(ticker_or_name, year):
    indicators = [
        "拨备覆盖率",
        "分红金额",
        "拨贷比_coverage",
        "分红率",
        "A股分红金额",
        "A股融资金额",
        "年度涨跌幅",
        "前五大客户收入占比",
        "前五大供应商采购占比",
        "上市募集资金总额",
        "支付新股发行费用",
        "每股分红"
    ]
    result = indicators_client.extract_indicators(
        ticker_or_name=ticker_or_name,
        year=year,
        form="年度报告",
        indicators=indicators
    )
    print(json.dumps(result, ensure_ascii=False))
 
if __name__ == "__main__":
    import sys
    import json
    if len(sys.argv) != 3:
        print("Usage: python script.py <ticker_or_name> <year>")
        sys.exit(1)
    ticker_or_name = sys.argv[1]
    year = int(sys.argv[2])
    main(ticker_or_name, year)