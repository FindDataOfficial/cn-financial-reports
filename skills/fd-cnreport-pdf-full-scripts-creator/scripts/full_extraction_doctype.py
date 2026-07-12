import indicators_client

def main(ticker, year):
    return indicators_client.extract_indicators(ticker, year)
