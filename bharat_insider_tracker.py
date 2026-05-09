# bharat_insider_tracker.py
# BHARATEDGE - Indian Insider Trading Tracker
# Uses multiple data sources for Indian stocks

import requests
import pandas as pd
from datetime import datetime, timedelta
import logging
import time
import json

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Accept': 'application/json, text/html',
}

# Map NSE symbols to US ADR tickers (for SEC data)
NSE_TO_ADR = {
    'INFY.NS'      : 'INFY',
    'WIT'          : 'WIPRO.NS',
    'HDB'          : 'HDFCBANK.NS',
    'IBN'          : 'ICICIBANK.NS',
    'TTM'          : 'TATAMOTORS.NS',
    'RDY'          : 'DRREDDY.NS',
    'SIFY'         : 'SIFY.NS',
}

# Reverse map for lookup
ADR_SYMBOLS = {v: k for k, v in NSE_TO_ADR.items()}


class BharatInsiderTracker:
    """
    Tracks insider trading for Indian stocks.
    Uses multiple free data sources.
    """

    def __init__(self):
        self.cache          = {}
        self.ticker_to_cik  = {}
        self._load_sec_tickers()

    def _load_sec_tickers(self):
        """Load SEC ticker to CIK mapping."""
        try:
            response = requests.get(
                'https://www.sec.gov/files/company_tickers.json',
                headers={
                    'User-Agent': 'BharatEdge contact@bharatedge.com'
                },
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                for key, val in data.items():
                    ticker = val.get('ticker', '').upper()
                    cik    = str(val.get('cik_str', '')).zfill(10)
                    if ticker:
                        self.ticker_to_cik[ticker] = cik
                print(f"   Loaded {len(self.ticker_to_cik)} tickers ✅")
        except Exception as e:
            logger.warning(f"SEC ticker load failed: {e}")

    def get_sec_filings(self, adr_symbol, days_back=30):
        """Get Form 4 filings for ADR symbol from SEC."""
        try:
            cik = self.ticker_to_cik.get(adr_symbol.upper())
            if not cik:
                return []

            url      = f"https://data.sec.gov/submissions/CIK{cik}.json"
            response = requests.get(
                url,
                headers={
                    'User-Agent': 'BharatEdge contact@bharatedge.com'
                },
                timeout=15
            )

            if response.status_code != 200:
                return []

            data    = response.json()
            filings = data.get('filings', {}).get('recent', {})
            forms   = filings.get('form', [])
            dates   = filings.get('filingDate', [])

            cutoff  = datetime.now() - timedelta(days=days_back)
            trades  = []

            for i, form in enumerate(forms):
                if form == '4':
                    try:
                        filing_date = datetime.strptime(
                            dates[i], '%Y-%m-%d'
                        )
                        if filing_date >= cutoff:
                            trades.append({
                                'date'  : dates[i],
                                'form'  : form,
                                'source': 'SEC'
                            })
                    except Exception:
                        continue

            return trades

        except Exception as e:
            logger.warning(f"SEC fetch failed for {adr_symbol}: {e}")
            return []

    def get_insider_score(self, symbol, days_back=30):
        """
        Get insider score for Indian stock.
        Checks ADR equivalent on SEC if available.
        """
        cache_key = f"{symbol}_{days_back}"
        if cache_key in self.cache:
            cached_time, score = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < 3600:
                return score

        score = 0.0

        # Check if Indian stock has US ADR
        adr_map = {
            'INFY.NS'      : 'INFY',
            'DRREDDY.NS'   : 'RDY',
            'WIPRO.NS'     : 'WIT',
            'HDFCBANK.NS'  : 'HDB',
            'ICICIBANK.NS' : 'IBN',
            'TATAMOTORS.NS': 'TTM',
            'SUNPHARMA.NS' : 'SUNPHY',
            'DIVISLAB.NS'  : 'DIVL',
        }

        adr_symbol = adr_map.get(symbol)

        if adr_symbol:
            trades = self.get_sec_filings(adr_symbol, days_back)
            count  = len(trades)

            if count >= 5:
                score = 0.15
            elif count >= 3:
                score = 0.10
            elif count >= 1:
                score = 0.05

            if score > 0:
                print(
                    f"   {symbol} (ADR:{adr_symbol}): "
                    f"+{score:.2f} ({count} SEC filings)"
                )

        self.cache[cache_key] = (datetime.now(), score)
        return score

    def get_bulk_scores(self, symbols, days_back=30):
        """Get insider scores for all Indian stocks."""
        scores = {}
        print(f"\n   Checking insider activity for {len(symbols)} stocks...")

        for symbol in symbols:
            try:
                score = self.get_insider_score(symbol, days_back)
                scores[symbol] = score

                if score >= 0.10:
                    print(f"   {symbol}: +{score:.2f} INSIDER BUYING! 🟢")
                elif score >= 0.05:
                    print(f"   {symbol}: +{score:.2f} Some activity 🟡")

                time.sleep(0.2)

            except Exception as e:
                scores[symbol] = 0.0

        active = sum(1 for s in scores.values() if s > 0)
        print(f"   Active insider stocks: {active}/{len(symbols)}")
        return scores


if __name__ == '__main__':
    print("\nTesting BharatEdge Insider Tracker...")
    tracker = BharatInsiderTracker()

    test_symbols = [
        'INFY.NS', 'DRREDDY.NS',
        'WIPRO.NS', 'HDFCBANK.NS',
        'ICICIBANK.NS', 'TATAMOTORS.NS'
    ]

    print("\n--- Individual Scores ---")
    for symbol in test_symbols:
        score = tracker.get_insider_score(symbol, days_back=30)
        print(f"{symbol}: Score={score:+.2f}")