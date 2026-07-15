# run_dashboard.py
# BHARAT EDGE — Dashboard Launcher with Heartbeat & Daily Health Report

"""
Starts the BharatEdge Bloomberg-style terminal dashboard.
Runs in parallel:
  - Heartbeat monitor: Telegram alert if scan is silent > 5 min
  - Daily health report: Telegram summary every day at 08:00 IST
"""

import os
import sys
import json
import threading
import time
import warnings
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ["PYTHONWARNINGS"]          = "ignore"
os.environ["TF_CPP_MIN_LOG_LEVEL"]   = "3"
os.environ["TOKENIZERS_PARALLELISM"]  = "false"
warnings.filterwarnings("ignore")
logging.getLogger("joblib").setLevel(logging.ERROR)
logging.getLogger("sklearn").setLevel(logging.ERROR)

ROOT          = Path(__file__).resolve().parent
LOG           = ROOT / "logs"
SCAN_FILE     = LOG / "scan_results.json"
TRADES_FILE   = LOG / "bharat_trades.json"
CIRCUIT_FILE  = LOG / "circuit_breaker.json"
STARTING_CAP  = 100_000.0
HEARTBEAT_S   = 300          # alert if scan older than 5 minutes
HEALTH_HOUR   = 8            # IST hour for daily report


# ── IST helpers ───────────────────────────────────────────────

def _ist_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)


def _safe_load(path: Path, default):
    bak = path.with_suffix(path.suffix + ".bak")
    for src in (path, bak):
        if src.exists():
            try:
                return json.loads(src.read_text(encoding="utf-8"))
            except Exception:
                continue
    return default


# ── Telegram sender (non-blocking, best-effort) ──────────────

def _send_telegram(msg: str) -> None:
    """Send via bharat_telegram.py's BharatTelegram class if available."""
    try:
        sys.path.insert(0, str(ROOT))
        from bharat_telegram import BharatTelegram
        tg = BharatTelegram()
        tg.send_message(msg)
    except Exception as e:
        print(f"[heartbeat] Telegram send failed: {e}")


def _inr(v: float) -> str:
    if abs(v) >= 1e7:
        return f"₹{v/1e7:.2f}Cr"
    if abs(v) >= 1e5:
        return f"₹{v/1e5:.2f}L"
    return f"₹{v:,.2f}"


# ── Heartbeat monitor thread ─────────────────────────────────

def _heartbeat_loop() -> None:
    """Alert via Telegram if scan file hasn't been updated in HEARTBEAT_S seconds."""
    alerted = False
    while True:
        try:
            scan = _safe_load(SCAN_FILE, {})
            scan_time = scan.get("scan_time")
            if scan_time:
                ts  = datetime.fromisoformat(scan_time)
                age = (datetime.now() - ts).total_seconds()
                if age > HEARTBEAT_S:
                    if not alerted:
                        msg = (
                            f"⚠️ *BharatEdge Heartbeat Alert*\n"
                            f"Scan engine has been silent for {int(age/60)} minutes.\n"
                            f"Last scan: `{scan_time[:19]}`\n"
                            f"Check GitHub Actions or cloud scanner."
                        )
                        _send_telegram(msg)
                        print(f"[heartbeat] ⚠️  Scan silent {int(age/60)}m — Telegram sent")
                        alerted = True
                else:
                    alerted = False   # reset once scan is fresh
            else:
                print("[heartbeat] No scan_time found in scan_results.json")
        except Exception as e:
            print(f"[heartbeat] error: {e}")
        time.sleep(60)   # check every minute


# ── Daily health report ───────────────────────────────────────

def _daily_health_loop() -> None:
    """Send a health report at HEALTH_HOUR:00 IST every day."""
    last_sent_date = None
    while True:
        try:
            ist = _ist_now()
            today = ist.date()
            if ist.hour == HEALTH_HOUR and last_sent_date != today:
                _send_health_report()
                last_sent_date = today
                print(f"[health] Daily report sent for {today}")
        except Exception as e:
            print(f"[health] error: {e}")
        time.sleep(55)   # check every ~minute


def _send_health_report() -> None:
    """Build and send the daily 8 AM IST health report."""
    try:
        port    = _safe_load(TRADES_FILE, {})
        circuit = _safe_load(CIRCUIT_FILE, {})
        scan    = _safe_load(SCAN_FILE, {})

        capital  = float(port.get("capital", STARTING_CAP))
        start    = float(port.get("starting_capital", STARTING_CAP))
        pos      = port.get("positions", {})
        history  = port.get("trade_history", [])

        pos_val = sum(
            p["shares"] * p.get("current_price", p.get("entry_price", 0))
            for p in pos.values()
        )
        total  = capital + pos_val
        pnl    = total - start
        pnl_pct = pnl / start * 100 if start else 0
        sign   = "+" if pnl >= 0 else ""

        sells  = [t for t in history if t.get("action") == "SELL"]
        wins   = sum(1 for t in sells if t.get("pnl", 0) > 0)
        wr     = wins / len(sells) * 100 if sells else 0

        regime  = scan.get("market_regime", {}).get("regime", "UNKNOWN")
        vix     = scan.get("market_regime", {}).get("vix", 0)
        n_sigs  = len(scan.get("signals", []))
        cb      = "🔴 TRIGGERED" if circuit.get("triggered") else "🟢 OK"

        ist_str = _ist_now().strftime("%d %b %Y, %H:%M IST")

        msg = (
            f"📊 *BharatEdge Daily Health Report*\n"
            f"_{ist_str}_\n\n"
            f"💼 *Portfolio*\n"
            f"  Total Value : `{_inr(total)}`\n"
            f"  Cash        : `{_inr(capital)}`\n"
            f"  Total P&L   : `{sign}{_inr(pnl)} ({sign}{pnl_pct:.2f}%)`\n"
            f"  Open Pos    : `{len(pos)}`\n\n"
            f"📈 *Performance*\n"
            f"  Closed Trades: `{len(sells)}`\n"
            f"  Win Rate     : `{wr:.0f}%`\n\n"
            f"🌐 *Market*\n"
            f"  Regime  : `{regime}`\n"
            f"  VIX     : `{vix:.1f}`\n"
            f"  Signals : `{n_sigs}` in last scan\n\n"
            f"⚡ Circuit Breaker: {cb}\n"
        )
        _send_telegram(msg)
    except Exception as e:
        _send_telegram(f"❌ BharatEdge health report failed: {e}")


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 54)
    print("  BHARAT EDGE  —  BLOOMBERG TERMINAL DASHBOARD")
    print("=" * 54)
    print()
    print("  Browser : http://localhost:8050")
    print("  NSE     : 9:15 – 15:30 IST (Mon–Fri)")
    print(f"  Refresh : 60s auto-refresh")
    print(f"  Health  : Daily report at {HEALTH_HOUR:02d}:00 IST via Telegram")
    print(f"  Heartbeat: Alert if scan silent > {HEARTBEAT_S//60} min")
    print()

    # Start background threads (daemon = stops with main process)
    hb = threading.Thread(target=_heartbeat_loop, daemon=True, name="heartbeat")
    hr = threading.Thread(target=_daily_health_loop, daemon=True, name="health")
    hb.start()
    hr.start()
    print("  [OK] Heartbeat monitor started")
    print("  [OK] Daily health thread started")
    print()

    from monitoring.dashboard import create_app
    app = create_app()
    app.run(debug=False, host="0.0.0.0", port=8050)
