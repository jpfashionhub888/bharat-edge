import yfinance as yf
ticker = yf.Ticker('^NSEI')
df = ticker.history(period='3mo')
print(f'Rows: {len(df)}')
print(df.tail(3))