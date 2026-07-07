# monitoring/model_watchdog.py
"""
BharatEdge Model Watchdog

Sends a 6-hour health report via Telegram covering:
  - Portfolio value & P&L (₹)
  - Trade progress (wins/losses/win rate/profit factor)
  - Model staleness (warns if models older than 7 days)
  - Last scan time (warns if no scan in >25h on a market day)
  - Circuit breaker status

Designed to run as a scheduled job (cron / GitHub Actions)
or as a daemon thread in a long-running process.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STALE_MODEL_DAYS  = 7    # warn if model file older than this
STALE_SCAN_HOURS  = 25   # warn if no scan log for this many hours on a market day
IST_OFFSET_H      = 5
IST_OFFSET_M      = 30


def _ist_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=IST_OFFSET_H, minutes=IST_OFFSET_M)


def _ist_str(dt: datetime | None = None) -> str:
    if dt is None:
        dt = _ist_now()
    return dt.strftime('%d %b %Y %H:%M IST')


def _is_market_day() -> bool:
    """Return True if today is Mon-Fri (approximate — ignores NSE holidays)."""
    return _ist_now().weekday() < 5   # 0=Mon … 4=Fri


# ── Model staleness ───────────────────────────────────────────────────

def _check_model_freshness(models_dir: str = 'saved_models') -> tuple[bool, str]:
    """
    Returns (is_stale, message).
    Checks the most recently modified .pkl file in models_dir.
    """
    try:
        pkl_files = list(Path(models_dir).glob('*.pkl'))
        if not pkl_files:
            return True, f'⚠️ No model files found in {models_dir}/'

        newest = max(pkl_files, key=lambda p: p.stat().st_mtime)
        age    = datetime.now() - datetime.fromtimestamp(newest.stat().st_mtime)
        days   = age.days

        if days >= STALE_MODEL_DAYS:
            return True, f'⚠️ Models stale: {newest.name} is {days}d old (retrain needed)'
        else:
            return False, f'✅ Models fresh: {newest.name} ({days}d old)'
    except Exception as e:
        return True, f'⚠️ Could not check model freshness: {e}'


# ── Last scan time ────────────────────────────────────────────────────

def _check_last_scan(log_file: str = 'logs/bharat_trades.json') -> tuple[bool, str]:
    """
    Returns (is_stale, message).
    Reads the last_updated field from bharat_trades.json.
    """
    try:
        with open(log_file) as f:
            data = json.load(f)
        saved_at = data.get('saved_at') or data.get('last_updated')
        if not saved_at:
            return True, '⚠️ No scan timestamp found in trade log'

        last = datetime.fromisoformat(saved_at.replace('Z', '+00:00'))
        age  = datetime.now(timezone.utc) - last.astimezone(timezone.utc)
        hours = age.total_seconds() / 3600

        if hours > STALE_SCAN_HOURS and _is_market_day():
            return True, f'⚠️ No scan in {hours:.0f}h (market day!) — check runner'
        else:
            last_ist = last.astimezone(timezone.utc) + timedelta(hours=IST_OFFSET_H, minutes=IST_OFFSET_M)
            return False, f'✅ Last scan: {last_ist.strftime("%d %b %H:%M IST")} ({hours:.0f}h ago)'
    except FileNotFoundError:
        return True, '⚠️ Trade log not found — no scans have run yet'
    except Exception as e:
        return True, f'⚠️ Could not check last scan: {e}'


# ── Portfolio snapshot ────────────────────────────────────────────────

def _get_portfolio_snapshot(trade_file: str = 'logs/bharat_trades.json') -> dict:
    """Read portfolio value and positions from trade log."""
    try:
        with open(trade_file) as f:
            data = json.load(f)
        capital   = data.get('capital', 0)
        start_cap = data.get('starting_capital', 100000)
        positions = data.get('positions', {})
        pnl       = capital - start_cap   # approximate (doesn't include open position value)
        return {
            'cash'        : capital,
            'starting'    : start_cap,
            'pnl'         : pnl,
            'n_positions' : len(positions),
            'positions'   : positions,
        }
    except Exception:
        return {}


# ── Trade stats ───────────────────────────────────────────────────────

def _get_trade_stats(trades_file: str = 'logs/closed_trades.json') -> dict:
    """Read closed trade summary."""
    try:
        with open(trades_file) as f:
            data = json.load(f)
        return data.get('summary', {})
    except Exception:
        return {}


# ── Circuit breaker ───────────────────────────────────────────────────

def _get_cb_status(cb_file: str = 'logs/circuit_breaker.json') -> str:
    try:
        with open(cb_file) as f:
            cb = json.load(f)
        if cb.get('triggered'):
            return f"🚨 TRIGGERED: {cb.get('trigger_reason', 'Unknown')}"
        return '✅ Clear'
    except Exception:
        return '❓ Unknown'


# ── Main report ───────────────────────────────────────────────────────

def run_watchdog_report(telegram=None) -> str:
    """
    Build and optionally send the 6-hour health report.

    Parameters
    ----------
    telegram : BharatTelegram instance (optional)

    Returns
    -------
    str : the formatted report message
    """

    # Portfolio
    pf      = _get_portfolio_snapshot()
    cash    = pf.get('cash', 0)
    start   = pf.get('starting', 100000)
    pnl     = pf.get('pnl', 0)
    n_pos   = pf.get('n_positions', 0)
    pnl_pct = (pnl / start * 100) if start else 0

    # Trade stats
    ts     = _get_trade_stats()
    total  = ts.get('total', 0)
    wins   = ts.get('wins', 0)
    wr     = ts.get('win_rate', 0) * 100
    pf_val = ts.get('profit_factor') or 0
    tpnl   = ts.get('total_pnl', 0)
    goal   = 50

    wr_flag = '✅' if wr >= 55 else ('⚠️' if total >= 10 else '❓')
    pf_flag = '✅' if pf_val >= 1.5 else ('⚠️' if total >= 10 else '❓')

    bar = '█' * min(total, 25) + '░' * (25 - min(total, 25))
    bar += f' {total}/{goal}'

    # Health checks
    model_stale, model_msg = _check_model_freshness()
    scan_stale,  scan_msg  = _check_last_scan()
    cb_status               = _get_cb_status()

    # Flags
    alerts = []
    if model_stale:
        alerts.append('⚠️ Models stale')
    if scan_stale and _is_market_day():
        alerts.append('⚠️ Scan missed')
    if cb_status.startswith('🚨'):
        alerts.append('🚨 Circuit breaker triggered')

    alert_block = '\n'.join(alerts) if alerts else '✅ All systems normal'

    sign_pnl  = '+' if pnl  >= 0 else ''
    sign_tpnl = '+' if tpnl >= 0 else ''

    report = (
        f'🤖 BharatEdge Watchdog Report\n'
        f'{"=" * 32}\n'
        f'⏰ {_ist_str()}\n'
        f'\n'
        f'💰 Portfolio\n'
        f'  Cash: ₹{cash:,.2f}\n'
        f'  P&L:  {sign_pnl}₹{pnl:,.2f} ({sign_pnl}{pnl_pct:.1f}%)\n'
        f'  Open positions: {n_pos}\n'
        f'\n'
        f'📉 Trade Progress ({total}/{goal})\n'
        f'  [{bar}]\n'
        f'  Win rate:   {wr_flag} {wr:.1f}%\n'
        f'  Profit fac: {pf_flag} {pf_val:.2f}\n'
        f'  Closed P&L: {sign_tpnl}₹{tpnl:,.2f}\n'
        f'\n'
        f'🔍 Health Checks\n'
        f'  {model_msg}\n'
        f'  {scan_msg}\n'
        f'  CB: {cb_status}\n'
        f'\n'
        f'🚦 Alerts\n'
        f'  {alert_block}'
    )

    if total >= goal:
        report += '\n\n🚀 50-trade milestone reached! Review live eligibility.'

    logger.info('Watchdog report generated — %d trades, wr=%.1f%%', total, wr)

    if telegram:
        try:
            telegram.send_message(report)
            logger.info('Watchdog report sent via Telegram')
        except Exception as e:
            logger.warning('Watchdog Telegram send failed: %s', e)

    return report


# ── Entry point (run as standalone script) ────────────────────────────

if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    from dotenv import load_dotenv
    load_dotenv()

    telegram = None
    try:
        from bharat_telegram import BharatTelegram
        telegram = BharatTelegram()
    except Exception:
        pass

    report = run_watchdog_report(telegram=telegram)
    print(report)
