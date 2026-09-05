# bharat_cloud_scan.py
# BHARAT EDGE - Cloud Scanner
# Runs on GitHub Actions 3x daily

import os
import sys
import warnings
import logging
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from bharat_market_regime import BharatMarketRegimeFilter
from risk_circuit_breaker import RiskCircuitBreaker
from critic_agent import CriticAgent
from bharat_mtf import BharatMTFAnalyzer
from bharat_correlation import BharatCorrelationFilter
from bharat_veto_agent import BharatVetoAgent
from bharat_insider_tracker import BharatInsiderTracker
from monitoring.command_listener import start_command_listener
from monitoring.trade_tracker import TradeTracker

warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['LOKY_MAX_CPU_COUNT'] = '1'

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

logger = logging.getLogger(__name__)
SCAN_STATUS_FILE = 'logs/scan_status.json'


def _write_scan_status(status, **details):
    """Persist scan lifecycle independently from the last good result."""
    os.makedirs(os.path.dirname(SCAN_STATUS_FILE) or '.', exist_ok=True)
    previous = {}
    try:
        with open(SCAN_STATUS_FILE, 'r', encoding='utf-8') as handle:
            loaded = json.load(handle)
            if isinstance(loaded, dict):
                previous = loaded
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    payload = {
        'status': status,
        'updated_at': datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(),
        'last_success_at': previous.get('last_success_at'),
        **details,
    }
    tmp_file = SCAN_STATUS_FILE + '.tmp'
    with open(tmp_file, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_file, SCAN_STATUS_FILE)
    try:
        import shutil
        backup_tmp = SCAN_STATUS_FILE + '.bak.tmp'
        shutil.copy2(SCAN_STATUS_FILE, backup_tmp)
        os.replace(backup_tmp, SCAN_STATUS_FILE + '.bak')
    except OSError as exc:
        logger.warning("Scan-status backup refresh failed: %s", exc)


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
    # TELEGRAM KILL SWITCH
    # ==========================================
    def _get_portfolio():
        """Portfolio getter for /status command."""
        cash    = trader.capital
        start   = trader.starting_capital
        n_pos   = len(trader.positions)
        pos_out = {}
        pos_value = 0.0
        for sym, pos in trader.positions.items():
            entry   = pos.get('entry_price', 0)
            qty     = pos.get('shares', 0)
            curr    = pos.get('current_price', entry)
            unreal  = (curr - entry) * qty if entry > 0 else 0.0
            pos_value += curr * qty
            pos_out[sym] = {
                'qty'           : qty,
                'avg_entry'     : entry,
                'unrealized_pnl': round(unreal, 2),
            }
        total_value = cash + pos_value
        return {
            'value'       : total_value,
            'cash'        : cash,
            'pnl'         : total_value - start,
            'n_positions' : n_pos,
            'positions'   : pos_out,
        }

    ctrl_state, listener = start_command_listener(get_portfolio_fn=_get_portfolio)
    listener.start()
    logger.info('Telegram command listener started')

    # Initialise trade tracker
    trade_tracker = TradeTracker(
        trades_file='logs/closed_trades.json',
        telegram=telegram,
    )
    trader.trade_tracker = trade_tracker

    # ==========================================
    # RISK CIRCUIT BREAKER CHECK
    # ==========================================
    print("\n" + "="*60)
    print("RISK CIRCUIT BREAKER")
    print("="*60)

    circuit_breaker = RiskCircuitBreaker()
    temp_value = trader.capital + sum(
        pos.get('shares', 0) * pos.get(
            'current_price', pos.get('entry_price', 0)
        )
        for pos in trader.positions.values()
    )

    circuit_triggered = circuit_breaker.check(
        current_value    = temp_value,
        starting_capital = trader.starting_capital,
        telegram         = telegram,
    )

    if circuit_triggered:
        print('   Trading suspended by circuit breaker!')

    # ── Kill-switch check ──────────────────────────────────────────────
    new_entries_blocked = circuit_triggered or ctrl_state.is_paused
    if ctrl_state.is_paused:
        print('\n⏸️  BOT PAUSED via Telegram /pause — new entries are disabled.')
        telegram.send_message(
            '⏸️ New entries are disabled — bot is paused. '
            'Existing positions will still be risk-managed.\n'
            'Send /resume to re-enable.'
        )

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
    from config.yfinance_runtime import configure_yfinance
    configure_yfinance(yf)
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
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df = df[['open', 'high', 'low', 'close', 'volume']].copy()
            df.dropna(inplace=True)
            stock_data[symbol] = df
            print(f"   [{i}/{len(all_stocks)}] {symbol} - {len(df)} rows")
        except Exception as e:
            print(f"   [{i}/{len(all_stocks)}] {symbol} - Failed: {e}")

    print(f"\n   Fetched {len(stock_data)}/{len(all_stocks)} stocks")
    price_coverage = len(stock_data) / len(all_stocks) if all_stocks else 0.0
    if price_coverage < 0.80:
        new_entries_blocked = True
        print(
            f"   DATA SAFETY: only {price_coverage:.1%} price coverage; "
            "blocking new entries (minimum 80%)."
        )

    live_market = dict(
        vix_value=None, vix_change=None, fii_net=0.0, dii_net=0.0,
        sgx_gap=0.0, news_sentiment=0.0, news_volume=0,
        _defaults_used=True,
        _data_quality={"status": "UNAVAILABLE", "critical_sources_available": False},
    )
    try:
        from phase6_market_data import get_live_market_context
        live_market, _ = get_live_market_context()
        print("   Validated market context loaded.")
    except Exception as exc:
        new_entries_blocked = True
        live_market["_data_quality"] = {
            "status": "UNAVAILABLE", "critical_sources_available": False,
            "reasons": [str(exc)],
        }
        print(f"   Market context failed ({exc}); blocking new entries.")

    # ==========================================
    # PHASE 2: SECTOR ROTATION
    # ==========================================
    print("\n" + "="*60)
    print("PHASE 2: SECTOR ROTATION")
    print("="*60)

    sector_scores = {}
    sector_snapshot = []
    try:
        from phase3_sector import run_sector_rotation
        if live_market.get('vix_value') is None:
            raise RuntimeError('validated India VIX unavailable; sector rotation withheld')
        rotation = run_sector_rotation(
            vix_value=float(live_market['vix_value']),
            fii_net=None,
            verbose=False
        )
        if not rotation.empty:
            for _, row in rotation.iterrows():
                sector_scores[row['sector']] = row['status']
                sector_snapshot.append({
                    'sector': str(row['sector']),
                    'status': str(row['status']),
                    'score': round(float(row['score']), 2),
                    'momentum_1w': round(float(row['mom_1w']), 2),
                    'momentum_1m': round(float(row['mom_1m']), 2),
                    'momentum_3m': round(float(row['mom_3m']), 2),
                    'relative_strength': round(float(row['rs_vs_nifty']), 2),
                    'trend_score': round(float(row['trend_score']), 2),
                    'volatility_score': round(float(row['vol_score']), 2),
                    'allocation_multiplier': round(float(row['alloc_mult']), 2),
                    'source': 'Yahoo Finance sector proxies + India VIX',
                })
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
    insider_tracker = BharatInsiderTracker()
    print("\n   Loading Indian insider data...")
    insider_scores = insider_tracker.get_bulk_scores(
        get_all_stocks(), days_back=30
    )

    # ==========================================
    # PHASE 3: ML MODELS + SIGNALS
    # ==========================================
    print("\n" + "="*60)
    print("PHASE 3: ML MODELS + SIGNALS")
    print("="*60)

    stock_signals = {}
    current_prices = {}
    model_info = {"status": "UNAVAILABLE", "files": []}

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
            trained = train_full_ensemble(
                symbols = all_symbols,
                period  = '6mo',  # Last 6 months only
            )
            if not trained:
                raise RuntimeError('Model retraining failed; cache was not advanced')
            mark_trained()
            print("   Models retrained and saved!")

        ensemble = load_all_models()
        from monitoring.integrity import model_provenance
        model_info = model_provenance('models')

        if ensemble:
            if live_market.get("_defaults_used"):
                new_entries_blocked = True
                print("   Market context is degraded; blocking new entries.")

            model_market = {
                key: value for key, value in live_market.items()
                if not key.startswith("_")
            }

            scan_df = run_full_scan(
                ensemble=ensemble,
                verbose=False,
                **model_market,
            )

            if scan_df is not None and not scan_df.empty:
                for _, row in scan_df.iterrows():
                    symbol = row['symbol']
                    signal_val = row.get('adj_confidence', 50) / 100
                    sector = get_sector_for_stock(symbol)
                    sector_status = sector_scores.get(sector, 'NEUTRAL')

                    if symbol in stock_data:
                        price = float(stock_data[symbol]['close'].iloc[-1])
                        price_as_of = stock_data[symbol].index[-1].isoformat()
                    else:
                        continue

                    current_prices[symbol] = price

                    sig = row.get('signal', 'HOLD')
                    # Downgrade BUY/STRONG_BUY signals in underweight sectors
                    if sector_status == 'UNDERWEIGHT' and sig in ('BUY', 'STRONG_BUY'):
                        sig = 'HOLD'

                    stock_signals[symbol] = {
                        'signal': sig,
                        'confidence': signal_val,
                        'sector': sector,
                        'sector_status': sector_status,
                        'price': price,
                        'price_source': 'Yahoo Finance',
                        'price_as_of': price_as_of,
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
        if (data['signal'] in ('BUY', 'STRONG_BUY')
                and market_regime['can_trade'] and not new_entries_blocked):
            price = data['price']

            # Log insider boost if available
            insider_score = insider_scores.get(symbol, 0.0)
            if insider_score > 0:
                print(f"   {symbol}: +{insider_score:.2f} insider boost!")

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
                reason=data['sector'],
                position_multiplier=float(
                    market_regime.get('position_multiplier', 1.0)
                ),
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
        fresh_position_prices = {
            symbol for symbol in trader.positions if symbol in current_prices
        }
        for symbol in list(trader.positions.keys()):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period='5d')
                if not df.empty and 'Close' in df.columns:
                    close_series = df['Close'].dropna()
                    if not close_series.empty:
                        price = float(close_series.iloc[-1])
                        current_prices[symbol] = price
                        fresh_position_prices.add(symbol)
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
            if symbol not in fresh_position_prices:
                print(f"   {symbol}: fresh price unavailable; risk update skipped")
                continue
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

    # current_prices already populated in Phase 5; ensure any newly opened
    # positions in this scan also have a fallback price.
    for symbol in list(trader.positions.keys()):
        if symbol not in current_prices:
            current_prices[symbol] = trader.positions[symbol].get('entry_price', 0)

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
    realized_pnl = sum(
        float(t.get('pnl', 0) or 0) for t in trader.trade_history
        if t.get('action') == 'SELL'
    )
    unrealized_pnl = total_pnl - realized_pnl
    from monitoring.equity_history import record_snapshot
    record_snapshot(total_value, realized_pnl, unrealized_pnl,
                    len(trader.positions), at=datetime.now(ZoneInfo('Asia/Kolkata')).isoformat())

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

    # ── Save scan results for dashboard ──────────────────────
    try:
        import json as _json
        _scan_out = {
            'scan_time'    : datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(),
            'market_regime': market_regime,
            'sectors'      : sector_snapshot,
            'data_quality'  : {
                'price_source': 'Yahoo Finance',
                'price_coverage': round(locals().get('price_coverage', 0.0), 4),
                'signal_count': len(stock_signals),
                'universe_count': len(all_stocks),
                'price_history_count': len(stock_data),
                'defaults_used': bool(locals().get('live_market', {}).get('_defaults_used', False)),
                'market_context': locals().get('live_market', {}).get('_data_quality', {}),
                'new_entries_blocked': bool(new_entries_blocked),
                'model_provenance': model_info,
            },
            'signals'      : [
                {
                    'symbol'       : sym,
                    'signal'       : d.get('signal', 'HOLD'),
                    'confidence'   : round(d.get('confidence', 0), 4),
                    'sector'       : d.get('sector', ''),
                    'sector_status': d.get('sector_status', 'NEUTRAL'),
                    'price'        : round(d.get('price', 0), 2),
                    'price_source' : d.get('price_source', 'Unknown'),
                    'price_as_of'  : d.get('price_as_of'),
                    'model_manifest': model_info.get('manifest_sha256'),
                }
                for sym, d in stock_signals.items()
            ],
        }
        import os as _os
        _os.makedirs('logs', exist_ok=True)
        _tmp = 'logs/scan_results.json.tmp'
        with open(_tmp, 'w') as _f:
            _json.dump(_scan_out, _f, indent=2)
            _f.flush()
            _os.fsync(_f.fileno())
        _os.replace(_tmp, 'logs/scan_results.json')
        import shutil as _shutil
        _backup_tmp = 'logs/scan_results.json.bak.tmp'
        _shutil.copy2('logs/scan_results.json', _backup_tmp)
        _os.replace(_backup_tmp, 'logs/scan_results.json.bak')
        print(f"   Scan results saved to logs/scan_results.json")
    except Exception as _e:
        raise RuntimeError(f"could not persist scan results: {_e}") from _e

    print("\n" + "="*60)
    print("BHARAT EDGE SCAN COMPLETE")
    print("="*60)
    print(f"   Price histories loaded: {len(stock_data)}/{len(all_stocks)}")
    print(f"   Qualifying signals: {len(stock_signals)}")
    print(f"   Open positions: {len(trader.positions)}")
    print(f"   Portfolio: Rs{total_value:,.2f}")
    print(f"   Total PnL: Rs{total_pnl:+,.2f} ({total_pct:+.1%})")

    # ==========================================
    # SUNDAY CRITIC REVIEW
    # ==========================================
    critic = CriticAgent()
    critic.run_weekly_review(
        trade_history    = trader.trade_history,
        portfolio_value  = total_value,
        starting_capital = trader.starting_capital,
        telegram_bot     = telegram,
    )

    listener.stop()

def main(force=False):
    day = datetime.now().strftime('%A')

    if day == 'Saturday' and not force:
        print(f"Saturday - Indian market closed.")
        return

    if day == 'Sunday':
        print(f"Sunday - Market closed but running Weekly Review...")

    started_at = datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()
    started_monotonic = time.monotonic()
    _write_scan_status('RUNNING', started_at=started_at, error=None)
    try:
        run_bharat_scan()
        finished_at = datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()
        _write_scan_status(
            'SUCCESS',
            started_at=started_at,
            last_success_at=finished_at,
            duration_seconds=round(time.monotonic() - started_monotonic, 2),
            error=None,
        )
        print("\nScan complete.")
    except Exception as e:
        try:
            _write_scan_status(
                'FAILED',
                started_at=started_at,
                duration_seconds=round(time.monotonic() - started_monotonic, 2),
                error=f'{type(e).__name__}: {e}'[:1000],
            )
        except Exception as status_error:
            logger.error("Could not persist failed scan status: %s", status_error)
        logger.error(f"Scan failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
