# phase2_features.py
# BHARAT EDGE - Phase 2 Feature Engineering Engine
# Complete file including build_live_row

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

import ta
from ta.trend import EMAIndicator, MACD, ADXIndicator, CCIIndicator
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

print("✅ phase2_features.py loaded")

# ============================================================
# SECTION 1: RAW DATA FETCHER
# ============================================================

def fetch_stock_data(symbol: str, period: str = "2y") -> pd.DataFrame:
    try:
        import time
        time.sleep(2)  # ✅ Add 2 second delay between requests

        ticker = yf.Ticker(symbol)
        df     = ticker.history(period=period)

        if df.empty or len(df) < 50:
            print(f"   ⚠️ Insufficient data for {symbol}")
            return pd.DataFrame()

        df.columns = [c.lower() for c in df.columns]
        df.index   = df.index.tz_localize(None)
        df         = df[['open','high','low','close','volume']].copy()
        df.dropna(inplace=True)

        print(f"   ✅ {symbol}: {len(df)} rows fetched")
        return df

    except Exception as e:
        print(f"   ❌ Error fetching {symbol}: {e}")
        return pd.DataFrame()


# ============================================================
# SECTION 2: PRICE ACTION FEATURES
# ============================================================

def add_price_action_features(df: pd.DataFrame) -> pd.DataFrame:
    df['returns_1d']  = df['close'].pct_change(1)
    df['returns_3d']  = df['close'].pct_change(3)
    df['returns_5d']  = df['close'].pct_change(5)
    df['returns_10d'] = df['close'].pct_change(10)
    df['returns_20d'] = df['close'].pct_change(20)

    df['high_low_range']   = (df['high'] - df['low']) / df['close']
    df['open_close_range'] = (df['close'] - df['open']) / df['open']
    df['body_size']        = abs(df['close'] - df['open']) / df['close']
    df['upper_shadow']     = (df['high'] - df[['open','close']].max(axis=1)) / df['close']
    df['lower_shadow']     = (df[['open','close']].min(axis=1) - df['low']) / df['close']
    df['gap']              = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)

    rolling_high = df['high'].rolling(20).max()
    rolling_low  = df['low'].rolling(20).min()
    df['price_position_20d'] = (
        (df['close'] - rolling_low) / (rolling_high - rolling_low + 1e-9)
    )

    print("   ✅ Price action features added (12 features)")
    return df


# ============================================================
# SECTION 3: TECHNICAL INDICATOR FEATURES
# ============================================================

def add_technical_features(df: pd.DataFrame) -> pd.DataFrame:

    # RSI
    df['rsi_14']      = RSIIndicator(df['close'], window=14).rsi()
    df['rsi_7']       = RSIIndicator(df['close'], window=7).rsi()
    df['rsi_21']      = RSIIndicator(df['close'], window=21).rsi()
    df['rsi_14_diff'] = df['rsi_14'] - 50

    # MACD
    macd_obj         = MACD(df['close'], window_slow=26,
                            window_fast=12, window_sign=9)
    df['macd']           = macd_obj.macd()
    df['macd_signal']    = macd_obj.macd_signal()
    df['macd_histogram'] = macd_obj.macd_diff()
    df['macd_cross']     = (df['macd'] > df['macd_signal']).astype(int)

    # Bollinger Bands
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_upper']    = bb.bollinger_hband()
    df['bb_lower']    = bb.bollinger_lband()
    df['bb_middle']   = bb.bollinger_mavg()
    df['bb_width']    = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    df['bb_position'] = (
        (df['close'] - df['bb_lower']) /
        (df['bb_upper'] - df['bb_lower'] + 1e-9)
    )

    # EMA
    df['ema_9']   = EMAIndicator(df['close'], window=9).ema_indicator()
    df['ema_21']  = EMAIndicator(df['close'], window=21).ema_indicator()
    df['ema_50']  = EMAIndicator(df['close'], window=50).ema_indicator()
    df['ema_200'] = EMAIndicator(df['close'], window=200).ema_indicator()

    df['ema_cross_9_21']   = (df['ema_9']  > df['ema_21']).astype(int)
    df['ema_cross_21_50']  = (df['ema_21'] > df['ema_50']).astype(int)
    df['ema_cross_50_200'] = (df['ema_50'] > df['ema_200']).astype(int)

    df['price_vs_ema50']  = (df['close'] - df['ema_50'])  / df['ema_50']
    df['price_vs_ema200'] = (df['close'] - df['ema_200']) / df['ema_200']

    # ATR
    df['atr_14'] = AverageTrueRange(
        df['high'], df['low'], df['close'], window=14
    ).average_true_range()
    df['atr_pct'] = df['atr_14'] / df['close']

    # ADX
    adx           = ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx']     = adx.adx()
    df['adx_pos'] = adx.adx_pos()
    df['adx_neg'] = adx.adx_neg()
    df['adx_diff'] = df['adx_pos'] - df['adx_neg']

    # Stochastic
    stoch = StochasticOscillator(
        df['high'], df['low'], df['close'], window=14, smooth_window=3
    )
    df['stoch_k']    = stoch.stoch()
    df['stoch_d']    = stoch.stoch_signal()
    df['stoch_cross'] = (df['stoch_k'] > df['stoch_d']).astype(int)

    # Williams %R
    df['williams_r'] = WilliamsRIndicator(
        df['high'], df['low'], df['close'], lbp=14
    ).williams_r()

    # CCI
    df['cci_20'] = CCIIndicator(
        df['high'], df['low'], df['close'], window=20
    ).cci()

    # OBV
    df['obv']      = OnBalanceVolumeIndicator(
        df['close'], df['volume']
    ).on_balance_volume()
    df['obv_ema']   = df['obv'].ewm(span=20).mean()
    df['obv_trend'] = (df['obv'] > df['obv_ema']).astype(int)

    # Volume
    df['volume_sma_20'] = df['volume'].rolling(20).mean()
    df['volume_ratio']  = df['volume'] / (df['volume_sma_20'] + 1e-9)
    df['volume_trend']  = (df['volume'] > df['volume_sma_20']).astype(int)

    print("   ✅ Technical features added (35 features)")
    return df


# ============================================================
# SECTION 4: TIME FEATURES
# ============================================================

def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df['day_of_week']   = df.index.dayofweek
    df['week_of_month'] = (df.index.day - 1) // 7 + 1
    df['month']         = df.index.month
    df['quarter']       = df.index.quarter

    df['is_monday']      = (df.index.dayofweek == 0).astype(int)
    df['is_friday']      = (df.index.dayofweek == 4).astype(int)
    df['is_expiry_week'] = (
        (df.index.dayofweek == 3) & (df.index.day >= 24)
    ).astype(int)
    df['is_month_end']    = (df.index.day >= 28).astype(int)
    df['is_budget_month'] = (df.index.month == 2).astype(int)

    print("   ✅ Time features added (9 features)")
    return df


# ============================================================
# SECTION 5: MARKET CONTEXT FEATURES
# ============================================================

def add_market_context_features(
    df             : pd.DataFrame,
    vix_value      : float = 15.0,
    vix_change     : float = 0.0,
    fii_net        : float = 0.0,
    dii_net        : float = 0.0,
    sgx_gap        : float = 0.0,
    news_sentiment : float = 0.0,
    news_volume    : int   = 0,
) -> pd.DataFrame:
    df['india_vix']        = vix_value
    df['vix_change']       = vix_change
    df['vix_high']         = int(vix_value > 20)
    df['vix_extreme']      = int(vix_value > 25)

    df['fii_net']          = fii_net
    df['dii_net']          = dii_net
    df['fii_dii_combined'] = fii_net + dii_net
    df['fii_positive']     = int(fii_net > 0)
    df['dii_positive']     = int(dii_net > 0)

    df['sgx_gap']          = sgx_gap
    df['sgx_positive']     = int(sgx_gap > 0)

    df['news_sentiment']   = news_sentiment
    df['news_volume']      = news_volume

    print("   ✅ Market context features added (13 features)")
    return df


# ============================================================
# SECTION 6: TARGET VARIABLE
# ============================================================

def add_target(
    df           : pd.DataFrame,
    forward_days : int   = 1,
    threshold    : float = 0.003,
) -> pd.DataFrame:
    df['forward_return'] = df['close'].pct_change(forward_days).shift(-forward_days)
    df['target_binary']  = (df['forward_return'] > threshold).astype(int)

    conditions = [
        df['forward_return'] >  threshold * 2,
        df['forward_return'] >  threshold,
        df['forward_return'] < -threshold * 2,
        df['forward_return'] < -threshold,
    ]
    choices = [2, 1, -2, -1]
    df['target_multi'] = np.select(conditions, choices, default=0)

    print(f"   ✅ Target variable added")
    print(f"      Forward days: {forward_days}")
    print(f"      Threshold: {threshold*100:.1f}%")
    print(f"      Binary distribution:")
    counts = df['target_binary'].value_counts()
    total  = len(df)
    for label, count in counts.items():
        pct = count / total * 100
        tag = "UP  " if label == 1 else "DOWN"
        print(f"         {tag}: {count} ({pct:.1f}%)")

    return df


# ============================================================
# SECTION 7: FULL PIPELINE (for training)
# ============================================================

def build_features(
    symbol         : str,
    period         : str   = "2y",
    forward_days   : int   = 1,
    threshold      : float = 0.003,
    vix_value      : float = 15.0,
    vix_change     : float = 0.0,
    fii_net        : float = 0.0,
    dii_net        : float = 0.0,
    sgx_gap        : float = 0.0,
    news_sentiment : float = 0.0,
    news_volume    : int   = 0,
    verbose        : bool  = True,
) -> pd.DataFrame:
    """
    TRAINING pipeline:
    Fetch → Features → Target → dropna → return
    """
    if verbose:
        print(f"\n{'='*50}")
        print(f"  Building features for: {symbol}")
        print(f"{'='*50}")

    df = fetch_stock_data(symbol, period)
    if df.empty:
        return pd.DataFrame()

    df = add_price_action_features(df)
    df = add_technical_features(df)
    df = add_time_features(df)
    df = add_market_context_features(
        df,
        vix_value=vix_value, vix_change=vix_change,
        fii_net=fii_net,     dii_net=dii_net,
        sgx_gap=sgx_gap,     news_sentiment=news_sentiment,
        news_volume=news_volume,
    )
    df = add_target(df, forward_days=forward_days, threshold=threshold)

    initial = len(df)
    df.dropna(inplace=True)
    dropped = initial - len(df)

    if verbose:
        print(f"\n   📊 Feature Summary:")
        print(f"      Total rows    : {len(df)}")
        print(f"      Dropped (NaN) : {dropped}")
        print(f"      Total columns : {len(df.columns)}")
        print(f"      ML features   : {len(get_feature_columns())}")

    return df


# ============================================================
# SECTION 8: FEATURE COLUMN REGISTRY
# ============================================================

def get_feature_columns() -> list:
    return [
        # Price Action (12)
        'returns_1d','returns_3d','returns_5d','returns_10d','returns_20d',
        'high_low_range','open_close_range','body_size',
        'upper_shadow','lower_shadow','gap','price_position_20d',

        # Technical - Momentum (10)
        'rsi_14','rsi_7','rsi_21','rsi_14_diff',
        'macd','macd_signal','macd_histogram','macd_cross',
        'stoch_k','stoch_d',

        # Technical - Trend (11)
        'ema_cross_9_21','ema_cross_21_50','ema_cross_50_200',
        'price_vs_ema50','price_vs_ema200',
        'adx','adx_pos','adx_neg','adx_diff',
        'bb_width','bb_position',

        # Technical - Volatility (2)
        'atr_pct','williams_r',

        # Technical - Volume (4)
        'obv_trend','volume_ratio','volume_trend','cci_20',

        # Time (9)
        'day_of_week','week_of_month','month','quarter',
        'is_monday','is_friday','is_expiry_week',
        'is_month_end','is_budget_month',

        # Market Context (13)
        'india_vix','vix_change','vix_high','vix_extreme',
        'fii_net','dii_net','fii_dii_combined',
        'fii_positive','dii_positive',
        'sgx_gap','sgx_positive',
        'news_sentiment','news_volume',
    ]


# ============================================================
# SECTION 9: FEATURE QUALITY ANALYZER
# ============================================================

def analyze_feature_quality(df: pd.DataFrame) -> pd.DataFrame:
    feat_cols = get_feature_columns()
    available = [c for c in feat_cols if c in df.columns]

    print(f"\n{'='*50}")
    print(f"  FEATURE QUALITY REPORT")
    print(f"{'='*50}")

    report = []
    for col in available:
        series  = df[col]
        missing = series.isna().sum()
        std     = series.std()
        corr    = series.corr(df['target_binary'])
        report.append({
            'feature'    : col,
            'missing'    : missing,
            'std'        : round(std, 4),
            'corr_target': round(corr, 4),
            'abs_corr'   : round(abs(corr), 4),
        })

    report_df = pd.DataFrame(report).sort_values('abs_corr', ascending=False)

    print(f"\n  Top 15 features by correlation with target:\n")
    print(f"  {'Feature':<25} {'Corr':>8} {'Std':>8} {'Missing':>8}")
    print(f"  {'-'*55}")
    for _, row in report_df.head(15).iterrows():
        print(
            f"  {row['feature']:<25} "
            f"{row['corr_target']:>8.4f} "
            f"{row['std']:>8.4f} "
            f"{row['missing']:>8}"
        )
    return report_df


# ============================================================
# SECTION 10: LIVE-SAFE FEATURE BUILDER
# ============================================================

def build_live_row(
    symbol         : str,
    vix_value      : float = 15.0,
    vix_change     : float = 0.0,
    fii_net        : float = 0.0,
    dii_net        : float = 0.0,
    sgx_gap        : float = 0.0,
    news_sentiment : float = 0.0,
    news_volume    : int   = 0,
) -> pd.DataFrame:
    """
    Build features for LIVE prediction (today's row).

    KEY DIFFERENCE from build_features():
    - Does NOT call dropna() on the full DataFrame
    - Last row is kept even though forward_return = NaN
    - We only need today's FEATURE values, not the target
    """
    try:
        # Step 1: Fetch
        df = fetch_stock_data(symbol, period="6mo")
        if df.empty:
            print(f"   ❌ No data for {symbol}")
            return pd.DataFrame()

        # Step 2: Add all features
        df = add_price_action_features(df)
        df = add_technical_features(df)
        df = add_time_features(df)
        df = add_market_context_features(
            df,
            vix_value=vix_value, vix_change=vix_change,
            fii_net=fii_net,     dii_net=dii_net,
            sgx_gap=sgx_gap,     news_sentiment=news_sentiment,
            news_volume=news_volume,
        )

        # Step 3: Select feature columns only (no target)
        feat_cols = get_feature_columns()
        available = [c for c in feat_cols if c in df.columns]

        if not available:
            print(f"   ❌ No feature columns found for {symbol}")
            return pd.DataFrame()

        # Step 4: Take last row — no dropna on full df!
        feat_df  = df[available].copy()
        feat_df  = feat_df.replace([np.inf, -np.inf], np.nan)

        last_row = feat_df.tail(1).copy()

        # Fill NaN using 60-day median
        col_medians = feat_df.tail(60).median()
        last_row    = last_row.fillna(col_medians)

        # Fill any still-remaining NaN with 0
        last_row    = last_row.fillna(0)

        if last_row.empty:
            print(f"   ❌ Empty last row for {symbol}")
            return pd.DataFrame()

        print(f"   ✅ Live row built: {symbol} "
              f"(date: {last_row.index[0].date()})")
        return last_row

    except Exception as e:
        print(f"   ❌ build_live_row error [{symbol}]: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


# ============================================================
# QUICK TEST
# ============================================================

if __name__ == "__main__":
    print("\n" + "🧠"*20)
    print("  BHARAT EDGE - FEATURE ENGINE TEST")
    print("🧠"*20)

    symbol = "TCS.NS"
    print(f"\n📊 Building training features for {symbol}...")
    df = build_features(
        symbol         = symbol,
        period         = "1y",
        vix_value      = 17.21,
        vix_change     = -4.9,
        fii_net        = 500,
        dii_net        = 300,
        sgx_gap        = 0.65,
        news_sentiment = 0.3,
        news_volume    = 35,
    )

    if not df.empty:
        report = analyze_feature_quality(df)
        print(f"\n  ✅ Training features OK: {len(df)} rows")

    print(f"\n📡 Building LIVE row for {symbol}...")
    live = build_live_row(
        symbol         = symbol,
        vix_value      = 17.21,
        vix_change     = -4.9,
        fii_net        = 500,
        dii_net        = 300,
        sgx_gap        = 0.65,
        news_sentiment = 0.3,
        news_volume    = 35,
    )

    if not live.empty:
        print(f"\n  ✅ Live row OK!")
        print(f"  Date  : {live.index[0].date()}")
        print(f"  Shape : {live.shape}")
        print(f"\n  Sample values:")
        for col in list(live.columns)[:10]:
            print(f"     {col:<25}: {live[col].values[0]:.4f}")
    else:
        print("  ❌ Live row failed!")