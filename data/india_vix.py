# data/india_vix.py

import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from config.settings import VIX_LEVELS, VIX_MULTIPLIERS
import logging

logger = logging.getLogger(__name__)


class IndiaVIXFetcher:
    """
    Fetches India VIX data.
    VIX tells us how fearful the market is.
    We use it to size our positions.

    VIX < 12:  Very calm, be aggressive
    VIX 12-16: Normal, normal positions
    VIX 16-20: Nervous, reduce positions
    VIX 20-25: Fearful, small positions
    VIX > 25:  Panic, stay in cash
    """

    def __init__(self):
        self.current_vix = None
        self.vix_history = None

    def fetch(self):
        """Fetch current India VIX."""

        try:
            ticker = yf.Ticker('^INDIAVIX')
            df = ticker.history(period='30d')

            if df.empty:
                logger.warning("VIX data empty")
                return self._get_default()

            current = float(df['Close'].iloc[-1])
            prev = float(df['Close'].iloc[-2])
            change = ((current - prev) / prev) * 100

            self.current_vix = current
            self.vix_history = df

            result = {
                'vix': current,
                'vix_change': change,
                'regime': self._get_regime(current),
                'multiplier': self._get_multiplier(current),
                'signal': self._get_signal(current),
            }

            self._print_summary(result)
            return result

        except Exception as e:
            logger.error(f"VIX fetch error: {e}")
            return self._get_default()

    def _get_regime(self, vix):
        """Get VIX regime name."""

        if vix < VIX_LEVELS['very_calm']:
            return 'very_calm'
        elif vix < VIX_LEVELS['normal']:
            return 'normal'
        elif vix < VIX_LEVELS['nervous']:
            return 'nervous'
        elif vix < VIX_LEVELS['fearful']:
            return 'fearful'
        else:
            return 'panic'

    def _get_multiplier(self, vix):
        """Get position size multiplier."""

        regime = self._get_regime(vix)
        return VIX_MULTIPLIERS.get(regime, 1.0)

    def _get_signal(self, vix):
        """Get trading signal based on VIX."""

        if vix < 12:
            return 'AGGRESSIVE'
        elif vix < 16:
            return 'NORMAL'
        elif vix < 20:
            return 'CAUTIOUS'
        elif vix < 25:
            return 'DEFENSIVE'
        else:
            return 'CASH'

    def _get_default(self):
        """Default if VIX fetch fails."""

        return {
            'vix': 16.0,
            'vix_change': 0.0,
            'regime': 'normal',
            'multiplier': 1.0,
            'signal': 'NORMAL',
        }

    def _print_summary(self, data):
        """Print VIX summary."""

        vix = data['vix']
        change = data['vix_change']
        signal = data['signal']

        if vix < 16:
            emoji = "🟢"
        elif vix < 20:
            emoji = "🟡"
        else:
            emoji = "🔴"

        print(f"\n   😰 India VIX:")
        print(
            f"      {emoji} VIX: {vix:.2f}"
            f" ({change:+.1f}%)"
            f" | Signal: {signal}"
        )
        print(
            f"      Position Multiplier:"
            f" {data['multiplier']}x"
        )