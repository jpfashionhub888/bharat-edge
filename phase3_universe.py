# phase3_universe.py
# BHARAT EDGE - Stock Universe + Sector Definitions
# 50+ NSE stocks across all 11 sectors

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

print("✅ phase3_universe.py loaded")

# ============================================================
# SECTION 1: COMPLETE STOCK UNIVERSE
# ============================================================

STOCK_UNIVERSE = {

    # ── IT SECTOR ─────────────────────────────────────────
    'IT': {
        'stocks': [
            'TCS.NS',
            'INFY.NS',
            'WIPRO.NS',
            'HCLTECH.NS',
            'TECHM.NS',
            'MPHASIS.NS',
            'PERSISTENT.NS',
            'LTIM.NS',
        ],
        'index'      : '^CNXit',
        'weight'     : 1.0,
        'beta'       : 0.9,
        'description': 'Information Technology',
    },

    # ── BANKING ───────────────────────────────────────────
    'BANKING': {
        'stocks': [
            'HDFCBANK.NS',
            'ICICIBANK.NS',
            'SBIN.NS',
            'KOTAKBANK.NS',
            'AXISBANK.NS',
            'INDUSINDBK.NS',
            'BANDHANBNK.NS',
            'FEDERALBNK.NS',
        ],
        'index'      : '^NSEBANK',
        'weight'     : 1.0,
        'beta'       : 1.1,
        'description': 'Banking & Finance',
    },

    # ── NBFC ──────────────────────────────────────────────
    'NBFC': {
        'stocks': [
            'BAJFINANCE.NS',
            'BAJAJFINSV.NS',
            'CHOLAFIN.NS',
            'MUTHOOTFIN.NS',
        ],
        'index'      : None,
        'weight'     : 0.8,
        'beta'       : 1.2,
        'description': 'Non-Banking Financial Companies',
    },

    # ── AUTO ──────────────────────────────────────────────
    'AUTO': {
        'stocks': [
            'MARUTI.NS',
            'TATAMOTORS.NS',
            'M&M.NS',
            'BAJAJ-AUTO.NS',
            'HEROMOTOCO.NS',
            'EICHERMOT.NS',
        ],
        'index'      : None,
        'weight'     : 0.9,
        'beta'       : 1.0,
        'description': 'Automobile & Auto Components',
    },

    # ── PHARMA ────────────────────────────────────────────
    'PHARMA': {
        'stocks': [
            'SUNPHARMA.NS',
            'DRREDDY.NS',
            'CIPLA.NS',
            'DIVISLAB.NS',
            'AUROPHARMA.NS',
            'TORNTPHARM.NS',
        ],
        'index'      : None,
        'weight'     : 0.8,
        'beta'       : 0.7,
        'description': 'Pharmaceuticals & Healthcare',
    },

    # ── ENERGY ────────────────────────────────────────────
    'ENERGY': {
        'stocks': [
            'RELIANCE.NS',
            'ONGC.NS',
            'NTPC.NS',
            'POWERGRID.NS',
        ],
        'index'      : None,
        'weight'     : 0.9,
        'beta'       : 0.8,
        'description': 'Energy & Power',
    },

    # ── METAL ─────────────────────────────────────────────
    'METAL': {
        'stocks': [
            'TATASTEEL.NS',
            'HINDALCO.NS',
            'JSWSTEEL.NS',
            'COALINDIA.NS',
        ],
        'index'      : None,
        'weight'     : 0.8,
        'beta'       : 1.3,
        'description': 'Metals & Mining',
    },

    # ── FMCG ──────────────────────────────────────────────
    'FMCG': {
        'stocks': [
            'HINDUNILVR.NS',
            'ITC.NS',
            'NESTLEIND.NS',
            'BRITANNIA.NS',
        ],
        'index'      : None,
        'weight'     : 0.7,
        'beta'       : 0.6,
        'description': 'Fast Moving Consumer Goods',
    },

    # ── INFRA ─────────────────────────────────────────────
    'INFRA': {
        'stocks': [
            'LT.NS',
            'ULTRACEMCO.NS',
            'ADANIPORTS.NS',
            'DLF.NS',
        ],
        'index'      : None,
        'weight'     : 0.9,
        'beta'       : 1.1,
        'description': 'Infrastructure & Real Estate',
    },

    # ── CONSUMER ──────────────────────────────────────────
    'CONSUMER': {
        'stocks': [
            'TITAN.NS',
            'ASIANPAINT.NS',
            'PIDILITIND.NS',
            'HAVELLS.NS',
        ],
        'index'      : None,
        'weight'     : 0.8,
        'beta'       : 0.8,
        'description': 'Consumer Discretionary',
    },

    # ── TELECOM ───────────────────────────────────────────
    'TELECOM': {
        'stocks': [
            'BHARTIARTL.NS',
            'INDUSTOWER.NS',
        ],
        'index'      : None,
        'weight'     : 0.7,
        'beta'       : 0.9,
        'description': 'Telecommunications',
    },
}

# ── Nifty 50 Index ────────────────────────────────────────
NIFTY50_SYMBOL  = '^NSEI'
SENSEX_SYMBOL   = '^BSESN'
INDIA_VIX_SYMBOL= '^INDIAVIX'


# ============================================================
# SECTION 2: HELPER FUNCTIONS
# ============================================================

def get_all_stocks() -> list:
    """Return flat list of all stocks in universe."""
    all_stocks = []
    for sector, data in STOCK_UNIVERSE.items():
        all_stocks.extend(data['stocks'])
    return list(set(all_stocks))


def get_sector_for_stock(symbol: str) -> str:
    """Return sector name for a given stock symbol."""
    for sector, data in STOCK_UNIVERSE.items():
        if symbol in data['stocks']:
            return sector
    return 'UNKNOWN'


def get_stocks_by_sector(sector: str) -> list:
    """Return list of stocks for a given sector."""
    return STOCK_UNIVERSE.get(sector, {}).get('stocks', [])


def get_all_sectors() -> list:
    """Return list of all sector names."""
    return list(STOCK_UNIVERSE.keys())


def print_universe_summary():
    """Print summary of stock universe."""
    print(f"\n{'='*55}")
    print(f"  📊 BHARAT EDGE STOCK UNIVERSE")
    print(f"{'='*55}")

    total = 0
    for sector, data in STOCK_UNIVERSE.items():
        count = len(data['stocks'])
        total += count
        print(f"  {sector:<12}: {count:>3} stocks  "
              f"β={data['beta']:.1f}  "
              f"({data['description']})")

    print(f"  {'─'*50}")
    print(f"  {'TOTAL':<12}: {total:>3} stocks")
    print(f"{'='*55}")


# ============================================================
# SECTION 3: UNIVERSE DATA FETCHER
# ============================================================

def fetch_universe_data(
    period  : str  = "1y",
    verbose : bool = True,
) -> dict:
    """
    Fetch OHLCV data for ALL stocks in universe.
    Returns dict: {symbol: DataFrame}
    """
    all_stocks = get_all_stocks()

    if verbose:
        print(f"\n{'='*55}")
        print(f"  📡 FETCHING UNIVERSE DATA")
        print(f"  Stocks : {len(all_stocks)}")
        print(f"  Period : {period}")
        print(f"{'='*55}")

    data    = {}
    success = 0
    failed  = 0

    for i, symbol in enumerate(all_stocks, 1):
        try:
            ticker = yf.Ticker(symbol)
            df     = ticker.history(period=period)

            if df.empty or len(df) < 30:
                if verbose:
                    print(f"  [{i:>2}/{len(all_stocks)}] "
                          f"⚠️  {symbol:<20} insufficient data")
                failed += 1
                continue

            df.columns = [c.lower() for c in df.columns]
            df.index   = df.index.tz_localize(None)
            df         = df[['open','high','low',
                              'close','volume']].copy()
            df.dropna(inplace=True)

            data[symbol] = df
            success += 1

            if verbose:
                sector = get_sector_for_stock(symbol)
                print(f"  [{i:>2}/{len(all_stocks)}] "
                      f"✅ {symbol:<20} "
                      f"{len(df):>4} rows  "
                      f"[{sector}]")

        except Exception as e:
            if verbose:
                print(f"  [{i:>2}/{len(all_stocks)}] "
                      f"❌ {symbol:<20} {str(e)[:30]}")
            failed += 1

    if verbose:
        print(f"\n  ✅ Success: {success}/{len(all_stocks)} stocks")
        print(f"  ❌ Failed : {failed}/{len(all_stocks)} stocks")

    return data


# ============================================================
# SECTION 4: SECTOR PERFORMANCE CALCULATOR
# ============================================================

def calculate_sector_returns(
    universe_data : dict,
    lookback_days : int = 20,
) -> pd.DataFrame:
    """
    Calculate recent returns for each sector.
    Used as input to sector rotation engine.
    """
    sector_returns = []

    for sector, config in STOCK_UNIVERSE.items():
        stocks       = config['stocks']
        stock_returns= []

        for symbol in stocks:
            if symbol not in universe_data:
                continue

            df = universe_data[symbol]
            if len(df) < lookback_days:
                continue

            # Calculate return over lookback period
            ret = (df['close'].iloc[-1] / df['close'].iloc[-lookback_days] - 1) * 100
            stock_returns.append(ret)

        if stock_returns:
            sector_returns.append({
                'sector'       : sector,
                'avg_return'   : np.mean(stock_returns),
                'median_return': np.median(stock_returns),
                'best_stock'   : max(stock_returns),
                'worst_stock'  : min(stock_returns),
                'stocks_count' : len(stock_returns),
                'positive_pct' : sum(1 for r in stock_returns if r > 0)
                                 / len(stock_returns) * 100,
                'beta'         : config['beta'],
                'description'  : config['description'],
            })

    df = pd.DataFrame(sector_returns)
    if not df.empty:
        df = df.sort_values('avg_return', ascending=False)
        df = df.reset_index(drop=True)

    return df


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":
    print("\n" + "🌍"*20)
    print("  BHARAT EDGE - UNIVERSE TEST")
    print("🌍"*20)

    # Print universe summary
    print_universe_summary()

    all_stocks = get_all_stocks()
    print(f"\n  Total unique stocks: {len(all_stocks)}")

    # Test sector lookup
    test_stocks = ['TCS.NS', 'SBIN.NS', 'SUNPHARMA.NS']
    print(f"\n  Sector lookup test:")
    for s in test_stocks:
        print(f"     {s:<20} → {get_sector_for_stock(s)}")

    # Fetch a small sample
    print(f"\n  Fetching sample data (3 stocks)...")
    sample = {}
    for sym in ['TCS.NS', 'INFY.NS', 'RELIANCE.NS']:
        try:
            ticker = yf.Ticker(sym)
            df     = ticker.history(period="1mo")
            df.columns = [c.lower() for c in df.columns]
            df.index   = df.index.tz_localize(None)
            sample[sym] = df
            print(f"     ✅ {sym}: {len(df)} rows")
        except Exception as e:
            print(f"     ❌ {sym}: {e}")

    print(f"\n  ✅ Universe module ready!")
    print(f"  Total stocks available: {len(all_stocks)}")