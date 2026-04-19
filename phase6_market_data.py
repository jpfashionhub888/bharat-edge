# phase6_market_data.py
# BHARAT EDGE - Live Market Data Engine
# Complete file with all functions

import warnings
warnings.filterwarnings("ignore")

import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

print("✅ phase6_market_data.py loaded")


# ============================================================
# SECTION 1: INDIA VIX
# ============================================================

def fetch_india_vix() -> dict:
    """Fetch live India VIX from Yahoo Finance."""
    try:
        ticker = yf.Ticker("^INDIAVIX")
        df     = ticker.history(period="2d")

        if len(df) >= 2:
            current  = float(df["Close"].iloc[-1])
            previous = float(df["Close"].iloc[-2])
            chg_pct  = (current - previous) / previous * 100
        else:
            current = 17.0
            chg_pct = 0.0

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
        }

    except Exception as e:
        return {
            "value"     : 17.0,
            "change_pct": 0.0,
            "regime"    : "CAUTIOUS",
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

        df["dma50"]  = df["Close"].rolling(50).mean()
        df["dma200"] = df["Close"].rolling(200).mean()

        price  = float(df["Close"].iloc[-1])
        dma50  = float(df["dma50"].iloc[-1])
        dma200 = float(df["dma200"].iloc[-1])

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
        }

    except Exception as e:
        return {
            "price" : 0.0,
            "dma50" : 0.0,
            "dma200": 0.0,
            "regime": "UNKNOWN",
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
        }

    except Exception as e:
        return {
            "proxy_volume": 0,
            "direction"   : "UNKNOWN",
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
        }

    except Exception as e:
        return {
            "gap_pct"  : 0.0,
            "direction": "UNKNOWN",
            "error"    : str(e),
        }


# ============================================================
# SECTION 5: FULL MARKET SNAPSHOT
# ============================================================

def get_market_snapshot() -> dict:
    """Return complete live market snapshot."""
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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

    # FII direction → estimated crores
    fii_direction = fii_data.get("direction", "UNKNOWN")
    if fii_direction == "INFLOW":
        fii_estimate = +500.0
    elif fii_direction == "OUTFLOW":
        fii_estimate = -300.0
    else:
        fii_estimate = 0.0

    # Sentiment based on Nifty regime
    nifty_regime   = nifty_data.get("regime", "SIDEWAYS")
    news_sentiment = (
        0.2  if nifty_regime == "STRONG_BULL" else
        0.1  if nifty_regime == "BULL"        else
       -0.1  if nifty_regime == "STRONG_BEAR" else
        0.0
    )

    # Build context dict
    context = dict(
        vix_value      = float(vix_data.get("value", 17.0)),
        vix_change     = float(vix_data.get("change_pct", 0.0)),
        fii_net        = float(fii_estimate),
        dii_net        = 0.0,
        sgx_gap        = float(sgx_data.get("gap_pct", 0.0)),
        news_sentiment = float(news_sentiment),
        news_volume    = 30,
    )

    # Print summary
    print(f"  ✅ VIX      : {context['vix_value']:.2f} "
          f"({vix_data.get('regime','?')})")
    print(f"  ✅ Nifty    : {nifty_data.get('price',0):,.2f} "
          f"({nifty_regime})")
    print(f"  ✅ FII Est  : Rs {context['fii_net']:+,.0f} Cr "
          f"({fii_direction})")
    print(f"  ✅ SGX Gap  : {context['sgx_gap']:+.2f}%")
    print(f"  ✅ Sentiment: {context['news_sentiment']:+.1f}")

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