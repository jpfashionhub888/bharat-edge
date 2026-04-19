# data/fii_dii_data.py

import warnings
warnings.filterwarnings('ignore')

import requests
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FIIDIIFetcher:
    """
    Fetches FII/DII flow data from NSE India.
    This is FREE and extremely powerful.

    FII buying heavily = Strong bullish signal
    FII selling heavily = Strong bearish signal
    DII buying = Market support signal
    """

    def __init__(self):
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                ' AppleWebKit/537.36'
            ),
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nseindia.com',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.data = None

    def _init_session(self):
        """Initialize NSE session."""
        try:
            self.session.get(
                'https://www.nseindia.com',
                timeout=10
            )
        except Exception as e:
            logger.warning(f"Session init failed: {e}")

    def fetch(self):
        """Fetch latest FII/DII data."""

        try:
            self._init_session()

            url = (
                'https://www.nseindia.com/api/'
                'fiidiiTradeReact'
            )

            response = self.session.get(
                url, timeout=15
            )

            if response.status_code != 200:
                logger.warning(
                    f"FII/DII fetch failed: "
                    f"{response.status_code}"
                )
                return self._get_default()

            data = response.json()

            if not data:
                return self._get_default()

            latest = data[0] if data else {}

            fii_net = float(
                str(latest.get('fiiNet', '0'))
                .replace(',', '')
                .replace('(', '-')
                .replace(')', '')
                or 0
            )

            dii_net = float(
                str(latest.get('diiNet', '0'))
                .replace(',', '')
                .replace('(', '-')
                .replace(')', '')
                or 0
            )

            result = {
                'fii_net': fii_net,
                'dii_net': dii_net,
                'date': latest.get('date', ''),
                'fii_signal': self._get_signal(fii_net),
                'dii_signal': self._get_signal(dii_net),
                'combined_signal': self._combined(
                    fii_net, dii_net
                ),
            }

            self.data = result
            self._print_summary(result)
            return result

        except Exception as e:
            logger.error(f"FII/DII error: {e}")
            return self._get_default()

    def _get_signal(self, net_value):
        """Convert net value to signal."""

        if net_value > 2000:
            return 'STRONG_BUY'
        elif net_value > 500:
            return 'BUY'
        elif net_value > -500:
            return 'NEUTRAL'
        elif net_value > -2000:
            return 'SELL'
        else:
            return 'STRONG_SELL'

    def _combined(self, fii, dii):
        """Combined FII + DII signal score."""

        score = (fii * 0.7 + dii * 0.3) / 1000
        score = max(-1.0, min(1.0, score))
        return round(score, 3)

    def _get_default(self):
        """Return neutral default if fetch fails."""

        return {
            'fii_net': 0.0,
            'dii_net': 0.0,
            'date': str(datetime.now().date()),
            'fii_signal': 'NEUTRAL',
            'dii_signal': 'NEUTRAL',
            'combined_signal': 0.0,
        }

    def _print_summary(self, data):
        """Print FII/DII summary."""

        fii = data['fii_net']
        dii = data['dii_net']
        sig = data['fii_signal']

        fii_emoji = "🟢" if fii > 0 else "🔴"
        dii_emoji = "🟢" if dii > 0 else "🔴"

        print(f"\n   💰 FII/DII Flow:")
        print(
            f"      {fii_emoji} FII Net:"
            f" Rs {fii:+,.0f} Cr | {sig}"
        )
        print(
            f"      {dii_emoji} DII Net:"
            f" Rs {dii:+,.0f} Cr"
            f" | {data['dii_signal']}"
        )
        print(
            f"      Combined Signal:"
            f" {data['combined_signal']:+.3f}"
        )