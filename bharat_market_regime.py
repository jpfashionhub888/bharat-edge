# bharat_market_regime.py
# BHARATEDGE - Market Regime Filter
# Uses NIFTY50 instead of SPY

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import logging
from config.yfinance_runtime import configure_yfinance

logger = logging.getLogger(__name__)
configure_yfinance(yf)


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
                return None
            close = df['Close'].dropna()
            return float(close.iloc[-1]) if not close.empty else None
        except Exception as exc:
            logger.warning("India VIX data error: %s", exc)
            return None

    def analyze(self):
        print("\n   Analyzing Indian market regime...")

        result = {
            'regime'         : 'UNKNOWN',
            'can_trade'      : False,
            'nifty_return_1m': 0.0,
            'nifty_return_3m': 0.0,
            'vix'            : None,
            'reason'         : 'Market data has not been validated',
            'recommendation' : 'NO NEW TRADES',
            'data_status'    : 'UNAVAILABLE',
            'position_multiplier': 0.0,
        }

        df = self.get_nifty_data()
        if df is None:
            result['reason'] = 'Nifty data unavailable; blocking new trades'
            print("   Could not fetch Nifty data. Blocking new trades.")
            return result

        close = df['close'].dropna()

        try:
            latest = pd.Timestamp(close.index[-1])
            if latest.tzinfo is not None:
                latest = latest.tz_convert(None)
            age_days = (pd.Timestamp.now().normalize() - latest.normalize()).days
        except (IndexError, TypeError, ValueError):
            age_days = 999
        if age_days < 0 or age_days > 4:
            result['reason'] = f'Nifty data is stale ({age_days} days old); blocking new trades'
            print(f"   Nifty data is stale ({age_days} days). Blocking new trades.")
            return result

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
        if vix is None:
            result['reason'] = 'India VIX unavailable; blocking new trades'
            print("   Could not fetch India VIX. Blocking new trades.")
            return result
        result['vix'] = vix
        result['data_status'] = 'LIVE'

        if ret_1m <= self.bear_threshold and vix >= self.vix_high:
            result['regime']        = 'BEAR'
            result['can_trade']     = False
            result['reason']        = (
                f"Bear market: NIFTY {ret_1m:.1%}, VIX={vix:.1f}"
            )
            result['recommendation']= 'CASH MODE - No new buys'
            result['position_multiplier'] = 0.0

        elif ret_1m <= self.bear_threshold:
            result['regime']        = 'BEAR'
            result['can_trade']     = False
            result['reason']        = (
                f"Market correction: NIFTY {ret_1m:.1%}"
            )
            result['recommendation']= 'CASH MODE - No new buys'
            result['position_multiplier'] = 0.0

        elif vix >= self.vix_extreme:
            result['regime']        = 'CRASH'
            result['can_trade']     = False
            result['reason']        = (
                f"Extreme fear: VIX={vix:.1f}"
            )
            result['recommendation']= 'CASH MODE - Extreme fear'
            result['position_multiplier'] = 0.0

        elif ret_1m <= self.recovery_threshold or vix >= self.vix_high:
            result['regime']        = 'CAUTION'
            result['can_trade']     = True
            result['reason']        = (
                f"Cautious: NIFTY {ret_1m:.1%}, VIX={vix:.1f}"
            )
            result['recommendation']= 'REDUCED TRADING'
            result['position_multiplier'] = 0.5

        else:
            result['regime']        = 'BULL'
            result['can_trade']     = True
            result['reason']        = (
                f"Bull market: NIFTY {ret_1m:.1%}, VIX={vix:.1f}"
            )
            result['recommendation']= 'TRADE NORMALLY'
            result['position_multiplier'] = 1.0

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
