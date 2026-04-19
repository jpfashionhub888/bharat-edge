# phase3_scanner.py
# BHARAT EDGE - Full Portfolio Scanner
# UPGRADED: Live market context from phase6_market_data

import warnings
warnings.filterwarnings('ignore')
import os
import sys

os.environ['LOKY_MAX_CPU_COUNT'] = '1'
os.environ['PYTHONWARNINGS']     = 'ignore'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import pandas as pd
import numpy as np
from datetime import datetime

from phase3_universe import (
    STOCK_UNIVERSE,
    get_all_stocks,
    get_sector_for_stock,
    print_universe_summary,
)
from phase3_sector import (
    run_sector_rotation,
    filter_stocks_by_rotation,
    get_allocation_multiplier,
)
from phase2_models import load_all_models
from phase2_features import build_live_row, get_feature_columns

print("✅ phase3_scanner.py loaded")


# ============================================================
# SECTION 1: SCANNER CONFIG
# ============================================================

SCANNER_CONFIG = {
    'min_confidence'    : 65.0,
    'strong_confidence' : 75.0,
    'top_n_signals'     : 10,
    'min_sector_status' : 'NEUTRAL',
    'require_all_agree' : False,
    'min_model_votes'   : 3,
}


# ============================================================
# SECTION 2: SINGLE STOCK SCANNER
# ============================================================

def scan_stock(
    symbol        : str,
    ensemble      : dict,
    rotation_df   : pd.DataFrame,
    vix_value     : float = 15.0,
    vix_change    : float = 0.0,
    fii_net       : float = 0.0,
    dii_net       : float = 0.0,
    sgx_gap       : float = 0.0,
    news_sentiment: float = 0.0,
    news_volume   : int   = 0,
) -> dict:
    """Scan a single stock for trading signals."""
    cfg           = SCANNER_CONFIG
    base_models   = ensemble['base_models']
    feature_names = ensemble['feature_names']

    sector = get_sector_for_stock(symbol)
    alloc  = get_allocation_multiplier(symbol, rotation_df)

    if alloc == 0.0:
        return {}

    try:
        live_df = build_live_row(
            symbol         = symbol,
            vix_value      = vix_value,
            vix_change     = vix_change,
            fii_net        = fii_net,
            dii_net        = dii_net,
            sgx_gap        = sgx_gap,
            news_sentiment = news_sentiment,
            news_volume    = news_volume,
        )
    except:
        return {}

    if live_df.empty:
        return {}

    row_data = {}
    for feat in feature_names:
        if feat in live_df.columns:
            val = float(live_df[feat].values[0])
            row_data[feat] = 0.0 if (
                np.isnan(val) or np.isinf(val)) else val
        else:
            row_data[feat] = 0.0

    X_row = pd.DataFrame([row_data], columns=feature_names)

    individual = {}
    for name, model in base_models.items():
        try:
            if hasattr(model, 'n_jobs'):
                model.n_jobs = 1
            prob = float(model.predict_proba(X_row)[0][1])
            individual[name] = prob
        except:
            individual[name] = 0.5

    avg_prob  = float(np.mean(list(individual.values())))
    direction = 'UP' if avg_prob >= 0.5 else 'DOWN'
    up_votes  = sum(1 for p in individual.values() if p >= 0.5)

    base_conf  = avg_prob if direction == 'UP' else (1 - avg_prob)
    agreement  = (up_votes / len(individual) if direction == 'UP'
                  else (len(individual) - up_votes) / len(individual))
    std_dev    = float(np.std(list(individual.values())))
    confidence = float(min(99, max(1,
        base_conf * 100
        + (agreement - 0.5) * 30
        - std_dev * 20
    )))

    if direction == 'UP':
        if confidence >= cfg['strong_confidence']:
            signal = 'STRONG_BUY'
        elif confidence >= cfg['min_confidence']:
            signal = 'BUY'
        else:
            signal = 'WEAK_BUY'
    else:
        if confidence >= cfg['strong_confidence']:
            signal = 'STRONG_SELL'
        elif confidence >= cfg['min_confidence']:
            signal = 'SELL'
        else:
            signal = 'WEAK_SELL'

    if confidence < cfg['min_confidence']:
        return {}
    if direction == 'UP' and up_votes < cfg['min_model_votes']:
        return {}
    if direction != 'UP':
        return {}

    sector_status = ''
    if not rotation_df.empty:
        row = rotation_df[rotation_df['sector'] == sector]
        if not row.empty:
            sector_status = row['status'].iloc[0]

    adj_confidence = confidence
    if sector_status == 'OVERWEIGHT':
        adj_confidence = min(99, confidence + 5)
    elif sector_status == 'UNDERWEIGHT':
        adj_confidence = max(1, confidence - 10)

    return {
        'symbol'          : symbol,
        'sector'          : sector,
        'sector_status'   : sector_status,
        'signal'          : signal,
        'direction'       : direction,
        'confidence'      : round(confidence, 1),
        'adj_confidence'  : round(adj_confidence, 1),
        'avg_prob'        : round(avg_prob * 100, 1),
        'up_votes'        : up_votes,
        'alloc_mult'      : alloc,
        'individual_probs': {
            k: round(v*100, 1) for k, v in individual.items()},
        'scan_date'       : datetime.now().strftime('%Y-%m-%d'),
        'scan_time'       : datetime.now().strftime('%H:%M:%S'),
    }


# ============================================================
# SECTION 3: FULL PORTFOLIO SCANNER
# ============================================================

def run_full_scan(
    ensemble       : dict,
    vix_value      : float = 15.0,
    vix_change     : float = 0.0,
    fii_net        : float = 0.0,
    dii_net        : float = 0.0,
    sgx_gap        : float = 0.0,
    news_sentiment : float = 0.0,
    news_volume    : int   = 0,
    verbose        : bool  = True,
) -> pd.DataFrame:
    """Scan ALL 50+ stocks and return ranked signals."""
    cfg = SCANNER_CONFIG

    print(f"\n{'='*60}")
    print(f"  BHARAT EDGE - FULL PORTFOLIO SCAN")
    print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
    print(f"{'='*60}")

    print(f"\n  Step 1/3: Running Sector Rotation...")
    rotation_df = run_sector_rotation(
        vix_value      = vix_value,
        fii_net        = fii_net,
        news_sentiment = news_sentiment,
        verbose        = True,
    )

    print(f"\n  Step 2/3: Filtering stocks by sector...")
    tradeable = filter_stocks_by_rotation(
        rotation_df,
        min_status = cfg['min_sector_status'],
    )
    print(f"  Tradeable stocks : {len(tradeable)} "
          f"(from {len(get_all_stocks())} universe)")

    print(f"\n  Step 3/3: Scanning {len(tradeable)} stocks...")
    print(f"  {'─'*55}")

    signals = []
    scanned = 0
    skipped = 0

    for symbol in tradeable:
        try:
            print(f"  Scanning {symbol:<22}", end=" ", flush=True)

            result = scan_stock(
                symbol         = symbol,
                ensemble       = ensemble,
                rotation_df    = rotation_df,
                vix_value      = vix_value,
                vix_change     = vix_change,
                fii_net        = fii_net,
                dii_net        = dii_net,
                sgx_gap        = sgx_gap,
                news_sentiment = news_sentiment,
                news_volume    = news_volume,
            )

            if result:
                direction = result['direction']
                sig       = result['signal']
                conf      = result['adj_confidence']
                status    = result['sector_status']
                emoji     = "BUY " if direction == 'UP' else "SELL"
                print(f">> {emoji} {sig:<14} "
                      f"conf={conf:.1f}%  [{status}]")
                signals.append(result)
                scanned += 1
            else:
                print("-- No signal")
                skipped += 1

        except Exception as e:
            print(f"!! Error: {str(e)[:30]}")
            skipped += 1

    if not signals:
        print(f"\n  No signals generated today!")
        return pd.DataFrame()

    signals_df = pd.DataFrame(signals)
    signals_df = signals_df.sort_values(
        'adj_confidence', ascending=False
    ).reset_index(drop=True)

    _print_scan_results(
        signals_df, rotation_df,
        scanned, skipped, vix_value
    )

    filename = (f"scan_"
                f"{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    signals_df.to_csv(filename, index=False)
    print(f"\n  Scan saved: {filename}")

    return signals_df


# ============================================================
# SECTION 4: RESULTS PRINTER
# ============================================================

def _print_scan_results(
    df          : pd.DataFrame,
    rotation_df : pd.DataFrame,
    scanned     : int,
    skipped     : int,
    vix_value   : float,
):
    cfg   = SCANNER_CONFIG
    top_n = min(cfg['top_n_signals'], len(df))

    print(f"\n{'='*75}")
    print(f"  SCAN RESULTS - "
          f"{datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*75}")
    print(f"  Scanned  : {scanned + skipped} stocks")
    print(f"  Signals  : {len(df)}")
    print(f"  Skipped  : {skipped}")
    print(f"  VIX      : {vix_value:.1f}")

    print(f"\n  TOP {top_n} SIGNALS")
    print(f"  {'─'*75}")
    print(f"  {'#':<3} {'Symbol':<14} {'Sector':<11} "
          f"{'Signal':<14} {'Conf':>7} "
          f"{'Votes':>6} {'XGB':>6} {'LGB':>6} "
          f"{'RF':>6} {'ET':>6} {'Mult':>6}")
    print(f"  {'─'*75}")

    for i, row in df.head(top_n).iterrows():
        p      = row.get('individual_probs', {})
        status = row.get('sector_status', '')
        s_tag  = ("[OW]" if status == 'OVERWEIGHT'
                  else "[N]" if status == 'NEUTRAL'
                  else "[UW]")
        votes  = f"{row.get('up_votes',0)}/4"
        mult   = f"{row['alloc_mult']:.1f}x"

        print(
            f"  {i+1:<3} "
            f"{row['symbol']:<14} "
            f"{s_tag}{row['sector']:<7} "
            f"{'>>':>2}{row['signal']:<12} "
            f"{row['adj_confidence']:>6.1f}% "
            f"{votes:>6} "
            f"{p.get('xgboost',0):>5.1f}% "
            f"{p.get('lightgbm',0):>5.1f}% "
            f"{p.get('random_forest',0):>5.1f}% "
            f"{p.get('extra_trees',0):>5.1f}% "
            f"{mult:>6}"
        )

    print(f"\n  SIGNALS BY SECTOR")
    print(f"  {'─'*45}")
    sector_counts = df.groupby('sector').size().sort_values(
        ascending=False)
    for sector, count in sector_counts.items():
        sector_df = df[df['sector'] == sector]
        avg_conf  = sector_df['adj_confidence'].mean()
        status    = sector_df['sector_status'].iloc[0]
        tag       = ("[OW]" if status == 'OVERWEIGHT'
                     else "[N]" if status == 'NEUTRAL'
                     else "[UW]")
        print(f"  {tag} {sector:<12}: "
              f"{count:>3} signals  "
              f"avg_conf={avg_conf:.1f}%")

    strong_buys = df[df['signal'] == 'STRONG_BUY']
    buys        = df[df['signal'] == 'BUY']
    overweight  = df[df['sector_status'] == 'OVERWEIGHT']

    print(f"\n  SUMMARY")
    print(f"  {'─'*45}")
    print(f"  STRONG_BUY signals : {len(strong_buys)}")
    print(f"  BUY signals        : {len(buys)}")
    print(f"  Overweight sector  : {len(overweight)} signals")
    print(f"  Avg confidence     : "
          f"{df['adj_confidence'].mean():.1f}%")
    if len(df) > 0:
        print(f"  Top signal         : "
              f"{df.iloc[0]['symbol']} "
              f"({df.iloc[0]['adj_confidence']:.1f}%)")


# ============================================================
# SECTION 5: DAILY REPORT GENERATOR
# ============================================================

def generate_daily_report(
    scan_df    : pd.DataFrame,
    rotation_df: pd.DataFrame,
    vix_value  : float,
    fii_net    : float,
    sgx_gap    : float,
) -> str:
    date_str = datetime.now().strftime('%A, %d %B %Y')
    time_str = datetime.now().strftime('%H:%M:%S')

    if vix_value < 15:
        regime = "BULLISH"
    elif vix_value < 20:
        regime = "CAUTIOUS"
    elif vix_value < 25:
        regime = "DEFENSIVE"
    else:
        regime = "BEARISH"

    sgx_str = (f"+{sgx_gap:.2f}%"
               if sgx_gap >= 0 else f"{sgx_gap:.2f}%")
    sgx_dir = "POSITIVE" if sgx_gap > 0 else "NEGATIVE"
    fii_str = f"Rs {fii_net:+,.0f} Cr"
    fii_dir = "BUYING" if fii_net > 0 else "SELLING"

    if not rotation_df.empty:
        ow = rotation_df[
            rotation_df['status'] == 'OVERWEIGHT'
        ]['sector'].tolist()
        uw = rotation_df[
            rotation_df['status'] == 'UNDERWEIGHT'
        ]['sector'].tolist()
        nt = rotation_df[
            rotation_df['status'] == 'NEUTRAL'
        ]['sector'].tolist()
    else:
        ow, uw, nt = [], [], []

    if not scan_df.empty:
        top5        = scan_df.head(5)
        total_sigs  = len(scan_df)
        strong_buys = len(scan_df[
            scan_df['signal'] == 'STRONG_BUY'])
        avg_conf    = f"{scan_df['adj_confidence'].mean():.1f}%"

        signals_str = ""
        for _, row in top5.iterrows():
            tag = "BUY" if row['direction'] == 'UP' else "SELL"
            signals_str += (
                f"\n    {tag}  {row['symbol']:<18} "
                f"{row['signal']:<14} "
                f"conf={row['adj_confidence']:.1f}%  "
                f"[{row['sector_status']}]"
            )
    else:
        signals_str = "\n    No signals today"
        total_sigs  = 0
        strong_buys = 0
        avg_conf    = "N/A"

    rotation_str = ""
    if not rotation_df.empty:
        for _, row in rotation_df.iterrows():
            tag = ("[OW]" if row['status'] == 'OVERWEIGHT'
                   else "[N] " if row['status'] == 'NEUTRAL'
                   else "[UW]")
            rotation_str += (
                f"\n    {tag} {row['sector']:<12} "
                f"Score={row['score']:.1f}  "
                f"1M={row['mom_1m']:+.1f}%  "
                f"3M={row['mom_3m']:+.1f}%  "
                f"RS={row['rs_vs_nifty']:+.1f}%  "
                f"-> {row['status']}"
            )

    report = f"""
{'='*55}
  BHARAT EDGE - DAILY REPORT
  {date_str}  {time_str}
{'='*55}

MARKET CONTEXT
  SGX Nifty  : {sgx_str} ({sgx_dir})
  India VIX  : {vix_value:.1f} -> {regime}
  FII Flow   : {fii_str} ({fii_dir})

SECTOR ROTATION
  BUY Sectors   : {', '.join(ow) if ow else 'None'}
  NEUTRAL       : {', '.join(nt) if nt else 'None'}
  AVOID Sectors : {', '.join(uw) if uw else 'None'}

SECTOR SCORES{rotation_str}

TOP SIGNALS TODAY{signals_str}

SCAN SUMMARY
  Total Signals  : {total_sigs}
  Strong Buy     : {strong_buys}
  Avg Confidence : {avg_conf}

{'='*55}
Bharat Edge AI - Auto Generated
Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*55}
"""
    return report


def print_telegram_preview(
    scan_df    : pd.DataFrame,
    rotation_df: pd.DataFrame,
    vix_value  : float,
    fii_net    : float,
    sgx_gap    : float,
):
    date_str  = datetime.now().strftime('%A, %d %B %Y')
    sgx_str   = (f"+{sgx_gap:.2f}%"
                 if sgx_gap >= 0 else f"{sgx_gap:.2f}%")
    fii_str   = f"Rs {fii_net:+,.0f} Cr"

    if not rotation_df.empty:
        ow = rotation_df[
            rotation_df['status'] == 'OVERWEIGHT'
        ]['sector'].tolist()
        uw = rotation_df[
            rotation_df['status'] == 'UNDERWEIGHT'
        ]['sector'].tolist()
    else:
        ow, uw = [], []

    if vix_value < 15:
        regime = "BULLISH"
    elif vix_value < 20:
        regime = "CAUTIOUS"
    else:
        regime = "DEFENSIVE"

    print(f"\n{'='*55}")
    print(f"  TELEGRAM PREVIEW")
    print(f"{'='*55}")
    print(f"  BHARAT EDGE DAILY REPORT")
    print(f"  {date_str}")
    print(f"  {'─'*40}")
    print(f"  MARKET CONTEXT")
    print(f"    SGX Nifty : {sgx_str}")
    print(f"    India VIX : {vix_value:.1f} ({regime})")
    print(f"    FII Flow  : {fii_str}")
    print(f"  SECTOR ROTATION")
    print(f"    BUY   : {', '.join(ow)}")
    print(f"    AVOID : {', '.join(uw)}")
    print(f"  TOP SIGNALS TODAY")

    if not scan_df.empty:
        for i, row in scan_df.head(5).iterrows():
            direction = "BUY " if row['direction'] == 'UP' else "SELL"
            status    = row.get('sector_status', '')
            tag       = ("(OW)" if status == 'OVERWEIGHT'
                         else "(N)" if status == 'NEUTRAL'
                         else "(UW)")
            print(f"    {direction} {row['symbol']:<18} "
                  f"{row['signal']:<14} "
                  f"{row['adj_confidence']:.1f}% {tag}")
    else:
        print(f"    No signals today")

    print(f"  {'─'*40}")
    print(f"  Bharat Edge AI")
    print(f"{'='*55}")


def export_signals(
    scan_df  : pd.DataFrame,
    filename : str = None,
) -> str:
    if scan_df.empty:
        return ""

    if filename is None:
        filename = (f"signals_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M')}"
                    f".csv")

    scan_df.to_csv(filename, index=False)
    print(f"\n  Signals exported: {filename}")
    return filename


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  BHARAT EDGE - PORTFOLIO SCANNER")
    print("="*55)

    print_universe_summary()

    print("\n  Loading ML models...")
    ensemble = load_all_models()
    if not ensemble:
        print("  ERROR: Run phase2_models.py first!")
        exit()

    print(f"  Models : {list(ensemble['base_models'].keys())}")
    print(f"  Features: {len(ensemble['feature_names'])}")

    # ✅ LIVE MARKET CONTEXT
    print("\n  Fetching live market context...")
    try:
        from phase6_market_data import get_live_market_context
        MARKET, SNAPSHOT = get_live_market_context()
        print("  ✅ Live market context loaded!")
    except Exception as e:
        print(f"  ⚠️ Live context failed: {e}")
        print("  Using default market context...")
        MARKET = dict(
            vix_value      = 17.21,
            vix_change     = -4.9,
            fii_net        = 500,
            dii_net        = 300,
            sgx_gap        = 0.65,
            news_sentiment = 0.3,
            news_volume    = 35,
        )

    # Run full scan
    scan_results = run_full_scan(
        ensemble = ensemble,
        verbose  = True,
        **MARKET,
    )

    # Generate reports
    if not scan_results.empty:
        rotation = run_sector_rotation(
            vix_value = MARKET['vix_value'],
            fii_net   = MARKET['fii_net'],
            verbose   = False,
        )

        report = generate_daily_report(
            scan_df    = scan_results,
            rotation_df= rotation,
            vix_value  = MARKET['vix_value'],
            fii_net    = MARKET['fii_net'],
            sgx_gap    = MARKET['sgx_gap'],
        )

        print(report)

        try:
            with open("daily_report.txt", "w",
                      encoding="utf-8") as f:
                f.write(report)
            print("  Report saved: daily_report.txt")
        except Exception as e:
            print(f"  Report save error: {e}")

        print_telegram_preview(
            scan_df    = scan_results,
            rotation_df= rotation,
            vix_value  = MARKET['vix_value'],
            fii_net    = MARKET['fii_net'],
            sgx_gap    = MARKET['sgx_gap'],
        )

        export_signals(scan_results)

        # ✅ AUTO SEND TO TELEGRAM
        try:
            from phase6_telegram import (
                send_daily_report,
                send_signal_alert,
            )
            print("\n  Sending to Telegram...")
            send_daily_report()
            send_signal_alert(scan_results, market_ctx=MARKET)
            print("  ✅ Telegram report sent!")
        except Exception as e:
            print(f"  ⚠️ Telegram send failed: {e}")

    else:
        print("\n  No signals generated today!")

    print(f"\n{'='*55}")
    print(f"  SCANNER COMPLETE!")
    print(f"{'='*55}")