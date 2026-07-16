# data/sgx_nifty.py

import warnings
warnings.filterwarnings('ignore')

import requests
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SGXNiftyFetcher:
    """
    Fetches SGX Nifty data for pre-market signal.
    Singapore trades Nifty futures before India opens.
    This gives us a 30-45 minute head start.

    SGX Nifty up = Indian market likely opens green
    SGX Nifty down = Indian market likely opens red
    """

    def __init__(self):
        self.data = None

    def fetch(self):
        """Fetch SGX Nifty current value."""

        try:
            import yfinance as yf
            ticker = yf.Ticker('NQ=F')
            info = ticker.fast_info

            nifty = yf.Ticker('^NSEI')
            nifty_df = nifty.history(period='2d')

            if nifty_df.empty:
                return self._get_default()

            nifty_prev_close = float(
                nifty_df['Close'].iloc[-2]
            )
            nifty_last = float(
                nifty_df['Close'].iloc[-1]
            )

            gap_pct = (
                (nifty_last - nifty_prev_close)
                / nifty_prev_close * 100
            )

            result = {
                'nifty_prev_close': nifty_prev_close,
                'nifty_last': nifty_last,
                'gap_pct': gap_pct,
                'signal': self._get_signal(gap_pct),
                'time': datetime.now().strftime(
                    '%H:%M IST'
                ),
            }

            self.data = result
            self._print_summary(result)
            return result

        except Exception as e:
            logger.error(f"SGX Nifty error: {e}")
            return self._get_default()

    def _get_signal(self, gap_pct):
        """Convert gap to signal."""

        if gap_pct > 0.5:
            return 'STRONG_POSITIVE'
        elif gap_pct > 0.2:
            return 'POSITIVE'
        elif gap_pct > -0.2:
            return 'NEUTRAL'
        elif gap_pct > -0.5:
            return 'NEGATIVE'
        else:
            return 'STRONG_NEGATIVE'

    def _get_default(self):
        """Default neutral signal."""

        return {
            'nifty_prev_close': 0.0,
            'nifty_last': 0.0,
            'gap_pct': 0.0,
            'signal': 'NEUTRAL',
            'time': datetime.now().strftime('%H:%M IST'),
        }

    def _print_summary(self, data):
        """Print SGX Nifty summary."""

        gap = data['gap_pct']
        signal = data['signal']

        if gap > 0:
            emoji = "🟢"
        elif gap < 0:
            emoji = "🔴"
        else:
            emoji = "⚪"

        print(f"\n   🇸🇬 Market Gap Signal:")
        print(
            f"      {emoji} Gap: {gap:+.2f}%"
            f" | Signal: {signal}"
        )