# bharat_cloud_scan.py
# BHARAT EDGE - Cloud Scanner
# Runs on GitHub Actions 3x daily

import os
import sys
import warnings
import logging
from datetime import datetime
from bharat_market_regime import BharatMarketRegimeFilter
from bharat_mtf import BharatMTFAnalyzer
from bharat_correlation import BharatCorrelationFilter
from bharat_veto_agent import BharatVetoAgent

warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['LOKY_MAX_CPU_COUNT'] = '1'

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

logger = logging.getLogger(__name__)


def is_market_day():
    """Check if today is a trading day (Mon-Fri)."""
    day = datetime.now().strftime('%A')
    return day not in ['Saturday', 'Sunday']


def run_bharat_scan():
    """Run complete BharatEdge scan with paper trading."""

    now = datetime.now()
    print("\n" + "="*60)
    print(f"BHARAT EDGE CLOUD SCAN - {now.strftime('%d %b %Y %H:%M IST')}")
    print("="*60)

    from bharat_telegram import BharatTelegram
    from bharat_paper_trader import BharatPaperTrader

    telegram = BharatTelegram()
    trader = BharatPaperTrader(
        starting_capital=100000.0,
        log_file='logs/bharat_trades.json'
    )
    trader.load_state()

    # ==========================================
    # PHASE 1: FETCH STOCK DATA
    # ==========================================
    print("\n" + "="*60)
    print("PHASE 1: FETCHING NSE STOCK DATA")
    print("="*60)

    from phase3_universe import get_all_stocks, get_sector_for_stock
    all_stocks = get_all_stocks()
    print(f"\n   Fetching data for {len(all_stocks)} NSE stocks...")

    import yfinance as yf
    import pandas as pd
    import numpy as np

    stock_data = {}
    for i, symbol in enumerate(all_stocks, 1):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period='2y')
            if df.empty or len(df) < 100 or df['Close'].isnull().all():
                print(f"   [!] Skipping {symbol} - No valid price data")
                continue
            df.columns = [c.lower() for c in df.columns]
            df.index = df.index.tz_localize(None)
            df = df[['open', 'high', 'low', 'close', 'volume']].copy()
            df.dropna(inplace=True)
            stock_data[symbol] = df
            print(f"   [{i}/{len(all_stocks)}] {symbol} - {len(df)} rows")
        except Exception as e:
            print(f"   [{i}/{len(all_stocks)}] {symbol} - Failed: {e}")

    print(f"\n   Fetched {len(stock_data)}/{len(all_stocks)} stocks")

    # ==========================================
    # PHASE 2: SECTOR ROTATION
    # ==========================================
    print("\n" + "="*60)
    print("PHASE 2: SECTOR ROTATION")
    print("="*60)

    sector_scores = {}
    try:
        from phase3_sector import run_sector_rotation
        rotation = run_sector_rotation(
            vix_value=17.0,
            fii_net=0,
            verbose=False
        )
        if not rotation.empty:
            for _, row in rotation.iterrows():
                sector_scores[row['sector']] = row['status']
                status_emoji = (
                    "BUY" if row['status'] == 'OVERWEIGHT'
                    else "AVOID" if row['status'] == 'UNDERWEIGHT'
                    else "NEUTRAL"
                )
                print(f"   {status_emoji} {row['sector']}")
    except Exception as e:
        print(f"   Sector rotation error: {e}")

    # ==========================================
    # PHASE 2B: MARKET REGIME CHECK
    # ==========================================
    print("\n" + "="*60)
    print("PHASE 2B: INDIAN MARKET REGIME FILTER")
    print("="*60)

    regime_filter = BharatMarketRegimeFilter()
    market_regime = regime_filter.analyze()

    if not market_regime['can_trade']:
        print(f"\n   CASH MODE ACTIVATED!")
        print(f"   Reason: {market_regime['reason']}")

    # ==========================================
    # MULTI-TIMEFRAME ANALYSIS
    # ==========================================
    print("\n" + "="*60)
    print("MULTI-TIMEFRAME ANALYSIS")
    print("="*60)

    mtf_analyzer = BharatMTFAnalyzer()
    mtf_scores   = {}

    if market_regime['can_trade']:
        print("\n   Checking timeframe alignment...")
        from phase3_universe import get_all_stocks
        all_stocks = get_all_stocks()
        for symbol in all_stocks:
            try:
                score = mtf_analyzer.get_mtf_score(symbol)
                mtf_scores[symbol] = score
                if score > 0:
                    print(f"   {symbol}: MTF {score:.0%} BULLISH")
            except Exception as e:
                mtf_scores[symbol] = 0.5

        bullish = sum(1 for s in mtf_scores.values() if s > 0)
        print(f"\n   MTF complete: {bullish} bullish stocks")
    else:
        for symbol in get_all_stocks():
            mtf_scores[symbol] = 0.5

    # Initialize Correlation Filter
    corr_filter = BharatCorrelationFilter(max_per_sector=2)
    veto_agent = BharatVetoAgent()

    # ==========================================
    # PHASE 3: ML MODELS + SIGNALS
    # ==========================================
    print("\n" + "="*60)
    print("PHASE 3: ML MODELS + SIGNALS")
    print("="*60)

    stock_signals = {}
    current_prices = {}

    try:
        from phase2_models import load_all_models
        from phase2_models import train_full_ensemble
        from phase3_scanner import run_full_scan
        from bharat_model_cache import should_retrain, mark_trained
        from phase3_universe import get_all_stocks

        # Walk-forward: Retrain every 30 days
        if should_retrain():
            print("\n   Retraining models (walk-forward)...")
            all_symbols = get_all_stocks()
            train_full_ensemble(
                symbols = all_symbols,
                period  = '6mo',  # Last 6 months only
            )
            mark_trained()
            print("   Models retrained and saved!")

        ensemble = load_all_models()

        if ensemble:
            scan_df = run_full_scan(
                ensemble=ensemble,
                verbose=False,
                vix_value=17.0,
                vix_change=0.0,
                fii_net=0.0,
                dii_net=0.0,
                sgx_gap=0.0,
                news_sentiment=0.0,
                news_volume=0,
            )

            if scan_df is not None and not scan_df.empty:
                for _, row in scan_df.iterrows():
                    symbol = row['symbol']
                    signal_val = row.get('adj_confidence', 50) / 100
                    sector = get_sector_for_stock(symbol)
                    sector_status = sector_scores.get(sector, 'NEUTRAL')

                    if symbol in stock_data:
                        price = float(stock_data[symbol]['close'].iloc[-1])
                    else:
                        continue

                    current_prices[symbol] = price

                    sig = row.get('signal', 'HOLD')
                    if sector_status == 'UNDERWEIGHT' and sig == 'BUY':
                        sig = 'HOLD'

                    stock_signals[symbol] = {
                        'signal': sig,
                        'confidence': signal_val,
                        'sector': sector,
                        'sector_status': sector_status,
                        'price': price,
                    }

                    print(
                        f"   {sig} {symbol}"
                        f" | {signal_val:.2f}"
                        f" | Rs{price:.2f}"
                        f" | {sector}"
                    )

    except Exception as e:
        print(f"   Model error: {e}")
        import traceback
        traceback.print_exc()

    # ==========================================
    # PHASE 4: EXECUTE TRADES
    # ==========================================
    print("\n" + "="*60)
    print("PHASE 4: EXECUTING PAPER TRADES")
    print("="*60)

    for symbol, data in stock_signals.items():
        if data['signal'] == 'BUY' and market_regime['can_trade']:
            price = data['price']

            # Multi-timeframe filter
            mtf_score = mtf_scores.get(symbol, 0.5)
            if mtf_score < 0.5:
                print(f"   {symbol}: BUY blocked by MTF filter")
                continue

            # Correlation filter
            if not corr_filter.can_add_position(
                symbol, trader.positions
            ):
                print(f"   {symbol}: BUY blocked by correlation filter")
                continue

            # AI Veto Agent Review
            veto_result = veto_agent.review_signal(
                symbol            = symbol,
                price             = price,
                confidence        = data['confidence'],
                sector            = data['sector'],
                market_regime     = market_regime['regime'],
                mtf_score         = mtf_scores.get(symbol, 0.5),
                current_positions = trader.positions,
                india_vix         = market_regime.get('vix', 15),
            )

            if veto_result['decision'] == 'VETO':
                print(
                    f"   {symbol}: VETOED by AI - "
                    f"{veto_result['reason']}"
                )
                continue

            # Calculate ATR
            atr = None

            opened = trader.open_position(
                symbol, price,
                data['confidence'],
                reason=data['sector']
            )
            if opened:
                telegram.alert_buy_signal(
                    symbol, price,
                    data['confidence'],
                    data['sector']
                )

    # ==========================================
    # PHASE 5: POSITION MANAGEMENT
    # ==========================================
    print("\n" + "="*60)
    print("PHASE 5: POSITION MANAGEMENT")
    print("="*60)

    if trader.positions:
        print("\n   Fetching current prices for open positions...")
        for symbol in list(trader.positions.keys()):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period='5d')
                if not df.empty and 'Close' in df.columns:
                    close_series = df['Close'].dropna()
                    if not close_series.empty:
                        price = float(close_series.iloc[-1])
                        current_prices[symbol] = price
                        print(f"   {symbol}: Rs{price:.2f}")
                    else:
                        current_prices[symbol] = trader.positions[symbol].get(
                            'entry_price', 0
                        )
                else:
                    current_prices[symbol] = trader.positions[symbol].get(
                        'entry_price', 0
                    )
            except Exception as e:
                print(f"   Could not fetch {symbol}: {e}")
                current_prices[symbol] = trader.positions[symbol].get(
                    'entry_price', 0
                )

        print("\n   Checking stop loss / take profit...")
        for symbol in list(trader.positions.keys()):
            if symbol in current_prices:
                pos = trader.positions.get(symbol, {})
                entry = pos.get('entry_price', 0)
                current = current_prices[symbol]
                pnl_pct = (current - entry) / entry * 100 if entry > 0 else 0

                print(
                    f"   {symbol}: "
                    f"Entry Rs{entry:.2f} | "
                    f"Now Rs{current:.2f} | "
                    f"PnL {pnl_pct:+.1f}%"
                )

                # Update current price and highest price
                trader.positions[symbol]['current_price'] = current
                if current > trader.positions[symbol].get('highest_price', 0):
                    trader.positions[symbol]['highest_price'] = current

                # Check stop loss / take profit / trailing stop
                trader.update_position(
                    symbol,
                    current,
                    stop_loss=0.03,
                    take_profit=0.08,
                    trailing_stop=0.025
                )

                # If position was closed send alert
                if symbol not in trader.positions:
                    if pnl_pct < 0:
                        pnl = (current - entry) * pos.get('shares', 0)
                        telegram.alert_stop_loss(symbol, current, pnl)
                        print(f"   STOP LOSS triggered for {symbol}!")
                    else:
                        pnl = (current - entry) * pos.get('shares', 0)
                        telegram.alert_take_profit(symbol, current, pnl)
                        print(f"   TAKE PROFIT triggered for {symbol}!")
    else:
        print("\n   No open positions to manage")
    # ==========================================
    # PHASE 6: PORTFOLIO SUMMARY + TELEGRAM
    # ==========================================

    # Force fetch current prices for ALL positions
    print("\n   Force fetching current prices for all positions...")
    for symbol in list(trader.positions.keys()):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period='5d')

            if not df.empty and 'Close' in df.columns:
                close_series = df['Close'].dropna()

                if not close_series.empty:
                    price = float(close_series.iloc[-1])
                    current_prices[symbol] = price
                    print(f"   {symbol}: Rs{price:.2f}")
                else:
                    current_prices[symbol] = trader.positions[symbol].get(
                        'entry_price', 0
                    )
            else:
                current_prices[symbol] = trader.positions[symbol].get(
                    'entry_price', 0
                )
            
        except Exception as e:
            print(f"   Could not fetch {symbol}: {e}")
            current_prices[symbol] = trader.positions[symbol].get(
                'entry_price', 0
            )

    print("\n" + "="*60)
    print("PHASE 6: PORTFOLIO SUMMARY")
    print("="*60)

    trader.get_summary(current_prices)

    # Update current prices in positions
    for symbol, pos in trader.positions.items():
        pos['current_price'] = current_prices.get(
            symbol, pos['entry_price']
        )

    trader.save_state()

    # Calculate real P&L safely
    position_value = 0.0
    for symbol, pos in trader.positions.items():
        shares = pos.get('shares', 0) or 0
        price = current_prices.get(
            symbol, pos.get('entry_price', 0)
        ) or pos.get('entry_price', 0) or 0
        position_value += shares * price

    total_value = (trader.capital or 0) + position_value
    if total_value <= 0 or total_value != total_value:
        total_value = trader.starting_capital

    total_pnl = total_value - trader.starting_capital
    total_pct = (total_pnl / trader.starting_capital) if trader.starting_capital > 0 else 0

    # Build positions with P&L for Telegram
    positions_with_pnl = {}
    for symbol, pos in trader.positions.items():
        curr_price = current_prices.get(
            symbol, pos.get('entry_price', 0)
        ) or pos.get('entry_price', 0) or 0
        entry_price = pos.get('entry_price', 0) or 0
        shares = pos.get('shares', 0) or 0
        
        if entry_price > 0:
            pnl = (curr_price - entry_price) * shares
            pnl_pct = (curr_price - entry_price) / entry_price
        else:
            pnl = 0.0
            pnl_pct = 0.0

        positions_with_pnl[symbol] = {
            **pos,
            'current_price': curr_price,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
        }
    telegram.alert_daily_summary(
        total_value, total_pnl, total_pct,
        positions_with_pnl, stock_signals
    )

    print("\n" + "="*60)
    print("BHARAT EDGE SCAN COMPLETE")
    print("="*60)
    print(f"   Stocks scanned: {len(stock_signals)}")
    print(f"   Open positions: {len(trader.positions)}")
    print(f"   Portfolio: Rs{total_value:,.2f}")
    print(f"   Total PnL: Rs{total_pnl:+,.2f} ({total_pct:+.1%})")


def main():
    if not is_market_day():
        day = datetime.now().strftime('%A')
        print(f"{day} - Indian market closed.")
        return

    try:
        run_bharat_scan()
        print("\nScan complete.")
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()