# phase3_sector.py
# BHARAT EDGE - Sector Rotation Engine
# Ranks sectors weekly and allocates capital to strongest

import warnings
warnings.filterwarnings('ignore')
import os
os.environ['LOKY_MAX_CPU_COUNT'] = '1'

import pandas as pd
import numpy as np
import yfinance as yf

from phase3_universe import (
    STOCK_UNIVERSE,
    get_all_stocks,
    get_sector_for_stock,
    calculate_sector_returns,
)

print("✅ phase3_sector.py loaded")


# ============================================================
# SECTION 1: SECTOR ROTATION CONFIG
# ============================================================

ROTATION_CONFIG = {
    # Momentum windows
    'momentum_1w'  : 5,    # 1 week
    'momentum_1m'  : 20,   # 1 month
    'momentum_3m'  : 60,   # 3 months

    # Weights for scoring
    'weight_1w'    : 0.40,
    'weight_1m'    : 0.35,
    'weight_3m'    : 0.25,

    # Relative strength weight
    'rs_weight'    : 0.30,

    # Allocation tiers
    'overweight_top'   : 3,   # Top 3 sectors = overweight
    'neutral_mid'      : 4,   # Next 4 = neutral
    'underweight_bot'  : 4,   # Bottom 4 = underweight/avoid

    # Capital allocation multipliers
    'overweight_mult'  : 1.5,  # 150% normal allocation
    'neutral_mult'     : 1.0,  # 100% normal allocation
    'underweight_mult' : 0.3,  # 30% normal allocation
    'avoid_mult'       : 0.0,  # 0% — skip sector

    # VIX regime adjustments
    'vix_low'    : 15,    # Bull regime
    'vix_mid'    : 20,    # Cautious regime
    'vix_high'   : 25,    # Bear regime
}


# ============================================================
# SECTION 2: SECTOR DATA FETCHER
# ============================================================

def fetch_sector_data(
    period  : str  = "6mo",
    verbose : bool = False,
) -> dict:
    """
    Fetch price data for representative stock per sector.
    Uses most liquid stock as sector proxy.
    """
    # Best proxy stock per sector
    sector_proxies = {
        'IT'      : 'TCS.NS',
        'BANKING' : 'HDFCBANK.NS',
        'NBFC'    : 'BAJFINANCE.NS',
        'AUTO'    : 'MARUTI.NS',
        'PHARMA'  : 'SUNPHARMA.NS',
        'ENERGY'  : 'RELIANCE.NS',
        'METAL'   : 'TATASTEEL.NS',
        'FMCG'    : 'HINDUNILVR.NS',
        'INFRA'   : 'LT.NS',
        'CONSUMER': 'TITAN.NS',
        'TELECOM' : 'BHARTIARTL.NS',
    }

    sector_data = {}
    for sector, symbol in sector_proxies.items():
        try:
            ticker = yf.Ticker(symbol)
            df     = ticker.history(period=period)
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                df.index   = df.index.tz_localize(None)
                df         = df[['open','high','low',
                                  'close','volume']].copy()
                df.dropna(inplace=True)
                sector_data[sector] = df
                if verbose:
                    print(f"     ✅ {sector:<12}: "
                          f"{symbol} ({len(df)} rows)")
        except Exception as e:
            if verbose:
                print(f"     ❌ {sector}: {e}")

    return sector_data


# ============================================================
# SECTION 3: NIFTY 50 FETCHER (Benchmark)
# ============================================================

def fetch_nifty_data(period: str = "6mo") -> pd.DataFrame:
    """Fetch Nifty 50 data for relative strength calculation."""
    try:
        ticker = yf.Ticker('^NSEI')
        df     = ticker.history(period=period)
        df.columns = [c.lower() for c in df.columns]
        df.index   = df.index.tz_localize(None)
        return df[['close']].copy()
    except:
        return pd.DataFrame()


# ============================================================
# SECTION 4: MOMENTUM CALCULATOR
# ============================================================

def calculate_momentum(
    df      : pd.DataFrame,
    window  : int,
) -> float:
    """Calculate price momentum over given window."""
    if df.empty or len(df) < window:
        return 0.0
    try:
        ret = (df['close'].iloc[-1] /
               df['close'].iloc[-window] - 1) * 100
        return float(ret)
    except:
        return 0.0


def calculate_relative_strength(
    sector_df : pd.DataFrame,
    nifty_df  : pd.DataFrame,
    window    : int = 20,
) -> float:
    """
    Calculate sector relative strength vs Nifty 50.
    RS > 0 means sector outperforming Nifty.
    RS < 0 means sector underperforming Nifty.
    """
    if sector_df.empty or nifty_df.empty:
        return 0.0

    try:
        # Align dates
        common = sector_df.index.intersection(nifty_df.index)
        if len(common) < window:
            return 0.0

        sector_ret = (sector_df.loc[common, 'close'].iloc[-1] /
                      sector_df.loc[common, 'close'].iloc[-window] - 1)
        nifty_ret  = (nifty_df.loc[common, 'close'].iloc[-1] /
                      nifty_df.loc[common, 'close'].iloc[-window] - 1)

        rs = (sector_ret - nifty_ret) * 100
        return float(rs)
    except:
        return 0.0


def calculate_trend_score(df: pd.DataFrame) -> float:
    """
    Calculate trend strength score (0-100).
    Based on EMA alignment.
    """
    if df.empty or len(df) < 50:
        return 50.0

    try:
        close  = df['close']
        ema20  = close.ewm(span=20).mean().iloc[-1]
        ema50  = close.ewm(span=50).mean().iloc[-1]
        price  = close.iloc[-1]

        score = 50.0
        if price > ema20:
            score += 15
        if price > ema50:
            score += 15
        if ema20 > ema50:
            score += 20

        return min(100, max(0, score))
    except:
        return 50.0


def calculate_volatility_score(df: pd.DataFrame) -> float:
    """
    Calculate volatility-adjusted score.
    Lower volatility = better score for risk management.
    """
    if df.empty or len(df) < 20:
        return 50.0

    try:
        returns    = df['close'].pct_change().dropna()
        volatility = returns.tail(20).std() * np.sqrt(252) * 100

        # Lower volatility = higher score
        if volatility < 15:
            return 80.0
        elif volatility < 25:
            return 65.0
        elif volatility < 35:
            return 50.0
        elif volatility < 50:
            return 35.0
        else:
            return 20.0
    except:
        return 50.0


# ============================================================
# SECTION 5: SECTOR SCORER
# ============================================================

def score_sector(
    sector    : str,
    df        : pd.DataFrame,
    nifty_df  : pd.DataFrame,
    vix_value : float = 15.0,
) -> dict:
    """
    Calculate comprehensive score for one sector.
    Score range: 0-100
    """
    cfg = ROTATION_CONFIG

    # Momentum scores
    mom_1w = calculate_momentum(df, cfg['momentum_1w'])
    mom_1m = calculate_momentum(df, cfg['momentum_1m'])
    mom_3m = calculate_momentum(df, cfg['momentum_3m'])

    # Weighted momentum
    weighted_mom = (
        mom_1w * cfg['weight_1w'] +
        mom_1m * cfg['weight_1m'] +
        mom_3m * cfg['weight_3m']
    )

    # Relative strength vs Nifty
    rs_1m = calculate_relative_strength(df, nifty_df, 20)
    rs_3m = calculate_relative_strength(df, nifty_df, 60)
    rs    = rs_1m * 0.6 + rs_3m * 0.4

    # Trend score
    trend_score = calculate_trend_score(df)

    # Volatility score
    vol_score = calculate_volatility_score(df)

    # VIX adjustment
    if vix_value > cfg['vix_high']:
        # Bear regime — favor defensive sectors
        defensive = ['PHARMA', 'FMCG', 'TELECOM']
        vix_adj   = 20 if sector in defensive else -20
    elif vix_value > cfg['vix_mid']:
        # Cautious — slight defensive tilt
        vix_adj   = 5
    else:
        # Bull regime — favor cyclicals
        cyclical  = ['BANKING', 'NBFC', 'AUTO', 'METAL', 'INFRA']
        vix_adj   = 15 if sector in cyclical else 0

    # Sector beta adjustment
    beta = STOCK_UNIVERSE[sector]['beta']
    if vix_value < cfg['vix_mid']:
        beta_adj = (beta - 1.0) * 10  # High beta good in bull
    else:
        beta_adj = (1.0 - beta) * 10  # Low beta good in bear

    # Final composite score
    raw_score = (
        weighted_mom * 0.40 +
        rs           * 0.25 +
        trend_score  * 0.20 +
        vol_score    * 0.10 +
        vix_adj      * 0.05
    )

    # Normalize to 0-100
    final_score = min(100, max(0, raw_score + 50))

    return {
        'sector'      : sector,
        'score'       : round(final_score, 2),
        'mom_1w'      : round(mom_1w, 2),
        'mom_1m'      : round(mom_1m, 2),
        'mom_3m'      : round(mom_3m, 2),
        'weighted_mom': round(weighted_mom, 2),
        'rs_vs_nifty' : round(rs, 2),
        'trend_score' : round(trend_score, 2),
        'vol_score'   : round(vol_score, 2),
        'vix_adj'     : round(vix_adj, 2),
        'beta_adj'    : round(beta_adj, 2),
        'description' : STOCK_UNIVERSE[sector]['description'],
    }


# ============================================================
# SECTION 6: SECTOR ROTATION ENGINE
# ============================================================

def run_sector_rotation(
    vix_value      : float = 15.0,
    fii_net        : float = 0.0,
    news_sentiment : float = 0.0,
    period         : str   = "6mo",
    verbose        : bool  = True,
) -> pd.DataFrame:
    """
    MAIN SECTOR ROTATION ENGINE.

    Scores all sectors and assigns:
    → OVERWEIGHT  (top 3)
    → NEUTRAL     (middle 4)
    → UNDERWEIGHT (bottom 4)
    """
    cfg = ROTATION_CONFIG

    if verbose:
        print(f"\n{'='*60}")
        print(f"  🔄 SECTOR ROTATION ENGINE")
        print(f"  VIX    : {vix_value:.1f}")
        print(f"  FII    : Rs {fii_net:+,.0f} Cr")
        print(f"  Period : {period}")
        print(f"{'='*60}")

    # Fetch data
    if verbose:
        print(f"\n  📡 Fetching sector data...")
    sector_data = fetch_sector_data(period=period, verbose=verbose)
    nifty_data  = fetch_nifty_data(period=period)

    if verbose:
        print(f"  📡 Fetching Nifty data: "
              f"{'✅' if not nifty_data.empty else '❌'}")

    # Score each sector
    scores = []
    for sector in STOCK_UNIVERSE.keys():
        if sector not in sector_data:
            continue
        score = score_sector(
            sector    = sector,
            df        = sector_data[sector],
            nifty_df  = nifty_data,
            vix_value = vix_value,
        )
        scores.append(score)

    if not scores:
        print("  ❌ No sector data available!")
        return pd.DataFrame()

    # Sort by score
    scores_df = pd.DataFrame(scores).sort_values(
        'score', ascending=False).reset_index(drop=True)

    # Assign rotation status
    n     = len(scores_df)
    top   = cfg['overweight_top']
    mid   = cfg['neutral_mid']

    statuses = []
    mults    = []
    for i in range(n):
        if i < top:
            statuses.append('OVERWEIGHT')
            mults.append(cfg['overweight_mult'])
        elif i < top + mid:
            statuses.append('NEUTRAL')
            mults.append(cfg['neutral_mult'])
        else:
            statuses.append('UNDERWEIGHT')
            mults.append(cfg['underweight_mult'])

    scores_df['status']     = statuses
    scores_df['alloc_mult'] = mults

    # FII adjustment
    if fii_net > 1000:
        # Strong FII buying — boost financial sectors
        for idx, row in scores_df.iterrows():
            if row['sector'] in ['BANKING', 'NBFC']:
                scores_df.at[idx, 'score'] += 5

    if verbose:
        _print_rotation_report(scores_df, vix_value)

    return scores_df


def _print_rotation_report(df: pd.DataFrame, vix_value: float):
    """Print formatted sector rotation report."""
    # VIX regime
    if vix_value < 15:
        regime = "🟢 BULL MARKET"
    elif vix_value < 20:
        regime = "🟡 CAUTIOUS"
    elif vix_value < 25:
        regime = "🟠 DEFENSIVE"
    else:
        regime = "🔴 BEAR MARKET"

    print(f"\n{'='*70}")
    print(f"  🔄 SECTOR ROTATION REPORT")
    print(f"  Market Regime: {regime} (VIX={vix_value:.1f})")
    print(f"{'='*70}")

    print(f"\n  {'Rank':<5} {'Sector':<12} {'Score':>7} "
          f"{'1W':>7} {'1M':>7} {'3M':>7} "
          f"{'RS':>7} {'Status':<14} {'Alloc'}")
    print(f"  {'-'*70}")

    status_emoji = {
        'OVERWEIGHT' : '🟢',
        'NEUTRAL'    : '🟡',
        'UNDERWEIGHT': '🔴',
    }

    for i, row in df.iterrows():
        emoji = status_emoji.get(row['status'], '⚪')
        mult  = f"{row['alloc_mult']:.1f}x"
        print(
            f"  {i+1:<5} "
            f"{row['sector']:<12} "
            f"{row['score']:>7.1f} "
            f"{row['mom_1w']:>+6.1f}% "
            f"{row['mom_1m']:>+6.1f}% "
            f"{row['mom_3m']:>+6.1f}% "
            f"{row['rs_vs_nifty']:>+6.1f}% "
            f"{emoji} {row['status']:<12} "
            f"{mult}"
        )

    print(f"\n  {'─'*70}")
    print(f"  🟢 OVERWEIGHT  → Increase allocation (1.5x)")
    print(f"  🟡 NEUTRAL     → Normal allocation (1.0x)")
    print(f"  🔴 UNDERWEIGHT → Reduce allocation (0.3x)")

    # Best sectors to trade today
    ow = df[df['status'] == 'OVERWEIGHT']['sector'].tolist()
    uw = df[df['status'] == 'UNDERWEIGHT']['sector'].tolist()

    print(f"\n  ✅ FOCUS ON   : {', '.join(ow)}")
    print(f"  ❌ AVOID      : {', '.join(uw)}")


# ============================================================
# SECTION 7: STOCK FILTER (uses sector rotation)
# ============================================================

def filter_stocks_by_rotation(
    rotation_df : pd.DataFrame,
    min_status  : str = 'NEUTRAL',
) -> list:
    """
    Filter stocks based on sector rotation status.
    Only return stocks from OVERWEIGHT or NEUTRAL sectors.
    """
    if rotation_df.empty:
        return get_all_stocks()

    if min_status == 'OVERWEIGHT':
        allowed = rotation_df[
            rotation_df['status'] == 'OVERWEIGHT'
        ]['sector'].tolist()
    else:
        allowed = rotation_df[
            rotation_df['status'].isin(['OVERWEIGHT', 'NEUTRAL'])
        ]['sector'].tolist()

    filtered = []
    for sector in allowed:
        stocks = STOCK_UNIVERSE.get(sector, {}).get('stocks', [])
        filtered.extend(stocks)

    return filtered


def get_allocation_multiplier(
    symbol      : str,
    rotation_df : pd.DataFrame,
) -> float:
    """Get capital allocation multiplier for a stock's sector."""
    if rotation_df.empty:
        return 1.0

    sector = get_sector_for_stock(symbol)
    row    = rotation_df[rotation_df['sector'] == sector]

    if row.empty:
        return 1.0

    return float(row['alloc_mult'].iloc[0])


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":
    print("\n" + "🔄"*20)
    print("  BHARAT EDGE - SECTOR ROTATION TEST")
    print("🔄"*20)

    # Run sector rotation
    rotation = run_sector_rotation(
        vix_value      = 17.21,
        fii_net        = 500,
        news_sentiment = 0.3,
        period         = "6mo",
        verbose        = True,
    )

    if not rotation.empty:
        # Get tradeable stocks
        tradeable = filter_stocks_by_rotation(
            rotation, min_status='NEUTRAL')

        print(f"\n  📊 Tradeable stocks: {len(tradeable)}")
        print(f"  Sectors allowed  : "
              f"{rotation[rotation['status']!='UNDERWEIGHT']['sector'].tolist()}")

        # Show allocation multipliers for sample stocks
        print(f"\n  📊 Allocation Multipliers:")
        for sym in ['TCS.NS','SBIN.NS','TATASTEEL.NS',
                    'BAJFINANCE.NS','SUNPHARMA.NS']:
            mult   = get_allocation_multiplier(sym, rotation)
            sector = get_sector_for_stock(sym)
            status = rotation[rotation['sector']==sector]['status'].values
            status = status[0] if len(status) > 0 else 'N/A'
            emoji  = ("🟢" if status == 'OVERWEIGHT'
                      else "🟡" if status == 'NEUTRAL'
                      else "🔴")
            print(f"     {sym:<20} {emoji} {status:<12} → {mult:.1f}x")

        print(f"\n  ✅ Sector Rotation Engine Ready!")