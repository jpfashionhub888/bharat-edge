# bharat_market_regime.py
# BHARATEDGE - Market Regime Filter
# Uses NIFTY50 instead of SPY

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BharatMarketRegimeFilter:
    """
    Detects Indian market regime.
    Uses NIFTY50 and India VIX.
    """

    def __init__(self):
        self.nifty_symbol = '^NSEI'      # Nifty 50
        self.vix_symbol   = '^INDIAVIX'  # India VIX

        self.bear_threshold     = -0.07
        self.recovery_threshold = -0.03
        self.vix_high           = 20
        self.vix_extreme        = 30

    def get_nifty_data(self):
        try:
            ticker = yf.Ticker(self.nifty_symbol)
            df     = ticker.history(period='3mo')
            if df.empty:
                return None
            df.columns = [c.lower() for c in df.columns]
            return df
        except Exception as e:
            logger.warning(f"Nifty data error: {e}")
            return None

    def get_india_vix(self):
        try:
            vix = yf.Ticker(self.vix_symbol)
            df  = vix.history(period='5d')
            if df.empty:
                return 15
            close = df['Close'].dropna()
            return float(close.iloc[-1])
        except Exception:
            return 15

    def analyze(self):
        print("\n   Analyzing Indian market regime...")

        result = {
            'regime'         : 'BULL',
            'can_trade'      : True,
            'nifty_return_1m': 0.0,
            'nifty_return_3m': 0.0,
            'vix'            : 15.0,
            'reason'         : 'Normal market conditions',
            'recommendation' : 'TRADE NORMALLY',
        }

        df = self.get_nifty_data()
        if df is None:
            print("   Could not fetch Nifty data. Allowing trades.")
            return result

        close = df['close'].dropna()

        if len(close) >= 21:
            ret_1m = (close.iloc[-1] - close.iloc[-21]) / close.iloc[-21]
            result['nifty_return_1m'] = float(ret_1m)
        else:
            ret_1m = 0.0

        if len(close) >= 63:
            ret_3m = (close.iloc[-1] - close.iloc[-63]) / close.iloc[-63]
            result['nifty_return_3m'] = float(ret_3m)
        else:
            ret_3m = 0.0

        vix = self.get_india_vix()
        result['vix'] = vix

        if ret_1m <= self.bear_threshold and vix >= self.vix_high:
            result['regime']        = 'BEAR'
            result['can_trade']     = False
            result['reason']        = (
                f"Bear market: NIFTY {ret_1m:.1%}, VIX={vix:.1f}"
            )
            result['recommendation']= 'CASH MODE - No new buys'

        elif ret_1m <= self.bear_threshold:
            result['regime']        = 'BEAR'
            result['can_trade']     = False
            result['reason']        = (
                f"Market correction: NIFTY {ret_1m:.1%}"
            )
            result['recommendation']= 'CASH MODE - No new buys'

        elif vix >= self.vix_extreme:
            result['regime']        = 'CRASH'
            result['can_trade']     = False
            result['reason']        = (
                f"Extreme fear: VIX={vix:.1f}"
            )
            result['recommendation']= 'CASH MODE - Extreme fear'

        elif ret_1m <= self.recovery_threshold or vix >= self.vix_high:
            result['regime']        = 'CAUTION'
            result['can_trade']     = True
            result['reason']        = (
                f"Cautious: NIFTY {ret_1m:.1%}, VIX={vix:.1f}"
            )
            result['recommendation']= 'REDUCED TRADING'

        else:
            result['regime']        = 'BULL'
            result['can_trade']     = True
            result['reason']        = (
                f"Bull market: NIFTY {ret_1m:.1%}, VIX={vix:.1f}"
            )
            result['recommendation']= 'TRADE NORMALLY'

        print(f"   Market Regime:    {result['regime']}")
        print(f"   NIFTY 1-Month:    {ret_1m:+.2%}")
        print(f"   India VIX:        {vix:.1f}")
        print(f"   Can Trade:        {result['can_trade']}")
        print(f"   Recommendation:   {result['recommendation']}")

        return result


if __name__ == '__main__':
    print("\nChecking Indian market regime...")
    f = BharatMarketRegimeFilter()
    result = f.analyze()
    print(f"\nFinal: {result['regime']} - {result['recommendation']}")