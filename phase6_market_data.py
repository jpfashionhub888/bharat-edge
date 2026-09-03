# phase6_market_data.py
# BHARAT EDGE - Live Market Data Engine
# Complete file with all functions

import warnings
warnings.filterwarnings("ignore")

import math
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta, timezone
from config.yfinance_runtime import configure_yfinance

configure_yfinance(yf)


class MarketDataUnavailable(RuntimeError):
    """Raised when critical market context cannot be authenticated."""


def _as_of(df) -> str | None:
    if df is None or df.empty:
        return None
    value = df.index[-1]
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _is_recent(as_of: str | None, max_age_days: int = 4) -> bool:
    if not as_of:
        return False
    try:
        observed = pd.Timestamp(as_of)
        now = pd.Timestamp.now(tz="UTC")
        if observed.tzinfo is None:
            observed = observed.tz_localize("UTC")
        else:
            observed = observed.tz_convert("UTC")
        return timedelta(days=0) <= now - observed <= timedelta(days=max_age_days)
    except (TypeError, ValueError):
        return False


# ============================================================
# SECTION 1: INDIA VIX
# ============================================================

def fetch_india_vix() -> dict:
    """Fetch live India VIX from Yahoo Finance."""
    try:
        ticker = yf.Ticker("^INDIAVIX")
        df     = ticker.history(period="2d")
        close = df["Close"].dropna() if "Close" in df else []

        if len(close) >= 2:
            current  = float(close.iloc[-1])
            previous = float(close.iloc[-2])
            if not math.isfinite(current) or not math.isfinite(previous) or previous <= 0:
                raise MarketDataUnavailable("India VIX returned invalid values")
            chg_pct  = (current - previous) / previous * 100 if previous else 0.0
        elif len(df) == 1:
            current = float(df["Close"].iloc[-1])
            chg_pct = 0.0
        else:
            raise MarketDataUnavailable("India VIX returned fewer than two valid observations")

        if current < 15:
            regime = "LOW_RISK"
        elif current < 20:
            regime = "CAUTIOUS"
        elif current < 25:
            regime = "HIGH_RISK"
        else:
            regime = "EXTREME"

        return {
            "value"     : round(float(current), 2),
            "change_pct": round(float(chg_pct), 2),
            "regime"    : regime,
            "available" : True,
            "source"    : "Yahoo Finance (^INDIAVIX)",
            "as_of"     : _as_of(df),
        }

    except Exception as e:
        return {
            "value"     : None,
            "change_pct": None,
            "regime"    : "UNKNOWN",
            "available" : False,
            "source"    : "Yahoo Finance (^INDIAVIX)",
            "as_of"     : None,
            "error"     : str(e),
        }


# ============================================================
# SECTION 2: NIFTY TREND
# ============================================================

def fetch_nifty_trend() -> dict:
    """Determine Nifty market regime using DMA."""
    try:
        ticker = yf.Ticker("^NSEI")
        df     = ticker.history(period="1y")

        if len(df) < 200 or df["Close"].dropna().shape[0] < 200:
            raise MarketDataUnavailable("Nifty returned fewer than 200 valid observations")

        df["dma50"]  = df["Close"].rolling(50).mean()
        df["dma200"] = df["Close"].rolling(200).mean()

        price  = float(df["Close"].iloc[-1])
        dma50  = float(df["dma50"].iloc[-1])
        dma200 = float(df["dma200"].iloc[-1])
        if not all(math.isfinite(value) and value > 0 for value in (price, dma50, dma200)):
            raise MarketDataUnavailable("Nifty returned invalid price or moving averages")

        if price > dma50 > dma200:
            regime = "STRONG_BULL"
        elif price > dma200:
            regime = "BULL"
        elif price < dma50 < dma200:
            regime = "STRONG_BEAR"
        else:
            regime = "SIDEWAYS"

        return {
            "price" : round(price, 2),
            "dma50" : round(dma50, 2),
            "dma200": round(dma200, 2),
            "regime": regime,
            "available": True,
            "source": "Yahoo Finance (^NSEI)",
            "as_of": _as_of(df),
        }

    except Exception as e:
        return {
            "price" : 0.0,
            "dma50" : 0.0,
            "dma200": 0.0,
            "regime": "UNKNOWN",
            "available": False,
            "source": "Yahoo Finance (^NSEI)",
            "as_of": None,
            "error" : str(e),
        }


# ============================================================
# SECTION 3: FII/DII PROXY
# ============================================================

def fetch_fii_dii_proxy() -> dict:
    """FII/DII proxy using NIFTYBEES ETF volume."""
    try:
        ticker = yf.Ticker("NIFTYBEES.NS")
        df     = ticker.history(period="5d")

        if len(df) >= 2:
            vol_today = float(df["Volume"].iloc[-1])
            vol_prev  = float(df["Volume"].iloc[-2])
            direction = "INFLOW" if vol_today > vol_prev else "OUTFLOW"
        else:
            vol_today = 0.0
            direction = "UNKNOWN"

        return {
            "proxy_volume": int(vol_today),
            "direction"   : direction,
            "available"   : len(df) >= 2,
            "is_proxy"    : True,
            "source"      : "Yahoo Finance NIFTYBEES volume proxy",
        }

    except Exception as e:
        return {
            "proxy_volume": 0,
            "direction"   : "UNKNOWN",
            "available"   : False,
            "is_proxy"    : True,
            "source"      : "Yahoo Finance NIFTYBEES volume proxy",
            "error"       : str(e),
        }


# ============================================================
# SECTION 4: SGX NIFTY PROXY
# ============================================================

def fetch_sgx_nifty_proxy() -> dict:
    """SGX proxy using overnight Nifty change."""
    try:
        ticker = yf.Ticker("^NSEI")
        df     = ticker.history(period="2d")

        if len(df) >= 2:
            current  = float(df["Close"].iloc[-1])
            previous = float(df["Close"].iloc[-2])
            gap_pct  = float((current - previous) / previous * 100)
        else:
            gap_pct = 0.0

        return {
            "gap_pct"  : round(gap_pct, 2),
            "direction": "POSITIVE" if gap_pct > 0 else "NEGATIVE",
            "available": len(df) >= 2,
            "is_proxy" : True,
            "source"   : "Nifty prior-session change (not GIFT Nifty)",
        }

    except Exception as e:
        return {
            "gap_pct"  : 0.0,
            "direction": "UNKNOWN",
            "available": False,
            "is_proxy" : True,
            "source"   : "Nifty prior-session change (not GIFT Nifty)",
            "error"    : str(e),
        }


# ============================================================
# SECTION 5: FULL MARKET SNAPSHOT
# ============================================================

def get_market_snapshot() -> dict:
    """Return complete live market snapshot."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix"      : fetch_india_vix(),
        "nifty"    : fetch_nifty_trend(),
        "fii_dii"  : fetch_fii_dii_proxy(),
        "sgx"      : fetch_sgx_nifty_proxy(),
    }


# ============================================================
# SECTION 6: LIVE MARKET CONTEXT (Ready-to-use dict)
# ============================================================

def get_live_market_context() -> tuple:
    """
    Returns ready-to-use MARKET dict for all modules.
    Replaces all hardcoded MARKET values.
    Returns (context_dict, snapshot_dict)
    """
    print("\n  Fetching live market context...")

    # Get full snapshot
    snapshot = get_market_snapshot()

    vix_data   = snapshot["vix"]
    nifty_data = snapshot["nifty"]
    fii_data   = snapshot["fii_dii"]
    sgx_data   = snapshot["sgx"]

    critical_errors = []
    if not vix_data.get("available"):
        critical_errors.append(f"VIX unavailable: {vix_data.get('error', 'no valid observations')}")
    elif not _is_recent(vix_data.get("as_of")):
        critical_errors.append("VIX observation is stale")
    if not nifty_data.get("available"):
        critical_errors.append(f"Nifty unavailable: {nifty_data.get('error', 'no valid observations')}")
    elif not _is_recent(nifty_data.get("as_of")):
        critical_errors.append("Nifty observation is stale")
    if critical_errors:
        raise MarketDataUnavailable("; ".join(critical_errors))

    # Volume direction is not an authenticated rupee FII/DII flow. Keep the
    # numerical feature neutral instead of inventing crore values.
    fii_direction = fii_data.get("direction", "UNKNOWN")
    degraded_reasons = ["FII/DII value unavailable; volume proxy excluded"]
    if sgx_data.get("is_proxy"):
        degraded_reasons.append("GIFT Nifty unavailable; prior-session proxy excluded")
    degraded_reasons.append("Authenticated news sentiment unavailable; neutral value used")

    # Nifty trend is not news sentiment. Keep this optional feature neutral
    # until an authenticated news-sentiment pipeline is available.
    nifty_regime   = nifty_data.get("regime", "SIDEWAYS")
    news_sentiment = 0.0

    # Build context dict
    context = dict(
        vix_value      = float(vix_data["value"]),
        vix_change     = float(vix_data["change_pct"]),
        fii_net        = 0.0,
        dii_net        = 0.0,
        sgx_gap        = 0.0,
        news_sentiment = float(news_sentiment),
        news_volume    = 0,
        _defaults_used = False,
        _data_quality  = {
            "status": "DEGRADED",
            "critical_sources_available": True,
            "reasons": degraded_reasons,
            "snapshot_time": snapshot["timestamp"],
        },
    )

    # Print summary
    print(f"  ✅ VIX      : {context['vix_value']:.2f} "
          f"({vix_data.get('regime','?')})")
    print(f"  ✅ Nifty    : {nifty_data.get('price',0):,.2f} "
          f"({nifty_regime})")
    print(f"  ⚠️ FII/DII : authenticated value unavailable ({fii_direction} proxy ignored)")
    print("  ⚠️ GIFT Nifty: unavailable (prior-session proxy ignored)")
    print("  ⚠️ News sentiment: authenticated feed unavailable (neutral)")

    return context, snapshot


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  BHARAT EDGE - LIVE MARKET DATA TEST")
    print("="*50)

    print("\n  Testing individual fetchers...")
    print(f"\n  VIX      : {fetch_india_vix()}")
    print(f"\n  Nifty    : {fetch_nifty_trend()}")
    print(f"\n  FII/DII  : {fetch_fii_dii_proxy()}")
    print(f"\n  SGX      : {fetch_sgx_nifty_proxy()}")

    print("\n" + "="*50)
    print("  Testing get_live_market_context()...")
    print("="*50)

    context, snapshot = get_live_market_context()

    print(f"\n  Final MARKET context:")
    for k, v in context.items():
        print(f"     {k:<20}: {v}")

    print(f"\n  ✅ Live market data working!")
    print(f"  ✅ Ready for cloud deployment!")
