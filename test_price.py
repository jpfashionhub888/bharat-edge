import yfinance as yf

ticker = yf.Ticker('COALINDIA.NS')
df = ticker.history(period='5d')
print(df[['Close']].tail())
print(f"\nLatest price: Rs{df['Close'].iloc[-1]:.2f}")
print(f"Entry price:  Rs443.15")
print(f"Difference:   Rs{df['Close'].iloc[-1] - 443.15:.2f}")