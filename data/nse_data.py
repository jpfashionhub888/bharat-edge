# data/nse_data.py

import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class NSEDataFetcher:
    """
    Fetches NSE/BSE stock data using yfinance.
    Handles Indian market specific quirks.
    Tested and verified working with Python 3.11.
    """

    def __init__(self, watchlist=None,
                 lookback_days=730):

        if watchlist is None:
            from config.settings import STOCK_WATCHLIST
            self.watchlist = [
                s for s in STOCK_WATCHLIST
                if not s.startswith('^')
            ]
        else:
            self.watchlist = watchlist

        self.lookback_days = lookback_days
        self.data_cache = {}

    def fetch_single(self, symbol):
        """Fetch data for one stock."""

        try:
            end = datetime.now()
            start = end - timedelta(days=self.lookback_days)

            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start,
                end=end,
                auto_adjust=True
            )

            if df.empty:
                logger.warning(f"No data for {symbol}")
                return pd.DataFrame()

            df.columns = [
                c.lower().replace(' ', '_')
                for c in df.columns
            ]

            keep = ['open', 'high', 'low', 'close', 'volume']
            existing = [c for c in keep if c in df.columns]
            df = df[existing].copy()

            df.index = df.index.tz_localize(None)
            df['symbol'] = symbol
            df['returns'] = df['close'].pct_change()
            df['log_returns'] = np.log(
                df['close'] / df['close'].shift(1)
            )

            df.dropna(subset=['close'], inplace=True)
            self.data_cache[symbol] = df

            logger.info(
                f"Fetched {len(df)} rows for {symbol}"
            )
            return df

        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return pd.DataFrame()

    def fetch_all(self):
        """Fetch data for all stocks."""

        n = len(self.watchlist)
        print(f"\n📊 Fetching {n} NSE/BSE stocks...")

        all_data = {}

        for i, symbol in enumerate(self.watchlist):
            print(
                f"   [{i+1}/{n}] {symbol}...",
                end=" "
            )
            df = self.fetch_single(symbol)

            if not df.empty:
                all_data[symbol] = df
                price = df['close'].iloc[-1]
                print(f"✅ Rs {price:,.2f}")
            else:
                print("❌ Failed")

        n_ok = len(all_data)
        print(f"\n✅ Fetched {n_ok}/{n} stocks")
        return all_data

    def get_combined(self):
        """Get all data in one DataFrame."""

        if not self.data_cache:
            self.fetch_all()

        frames = list(self.data_cache.values())
        if frames:
            return pd.concat(frames)
        return pd.DataFrame()

    def get_latest_prices(self):
        """Get latest price for each stock."""

        latest = {}
        for symbol, df in self.data_cache.items():
            if not df.empty:
                latest[symbol] = {
                    'price': df['close'].iloc[-1],
                    'change': df['returns'].iloc[-1],
                    'volume': df['volume'].iloc[-1],
                }
        return latest