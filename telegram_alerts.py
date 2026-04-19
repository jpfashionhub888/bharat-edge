# telegram_alerts.py
# BHARAT EDGE - Smart Telegram Alerts
# Only sends alerts when strong signals are found

import os
import requests
import pandas as pd
from datetime import datetime
from performance_tracker import get_performance_summary

# ============================================================
# CREDENTIALS
# ============================================================
TOKEN   = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# ============================================================
# THRESHOLDS
# ============================================================
STRONG_SIGNAL_THRESHOLD = 65.0   # Only alert if confidence > 65%
MIN_VOTES               = 3      # Only alert if at least 3/4 models agree

# ============================================================
# CORE SEND FUNCTIONS
# ============================================================

def send_message(text: str) -> bool:
    """Send a text message to Telegram."""
    if not TOKEN or not CHAT_ID:
        print(f"  [TELEGRAM] {text[:80]}")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={
                "chat_id"   : CHAT_ID,
                "text"      : text,
                "parse_mode": "HTML",
            },
            timeout=15,
        )
        ok = resp.json().get('ok', False)
        if ok:
            print(f"  ✅ Telegram sent!")
        else:
            print(f"  ❌ Telegram failed: {resp.json()}")
        return ok
    except Exception as e:
        print(f"  ❌ Telegram error: {e}")
        return False


def send_document(path: str) -> bool:
    """Send a file to Telegram."""
    if not TOKEN or not CHAT_ID or not os.path.exists(path):
        return False
    try:
        with open(path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendDocument",
                files={"document": f},
                data={"chat_id": CHAT_ID},
                timeout=30,
            )
        ok = resp.json().get('ok', False)
        if ok:
            print(f"  ✅ File sent: {path}")
        return ok
    except Exception as e:
        print(f"  ❌ File error: {e}")
        return False


# ============================================================
# ALERT FUNCTIONS
# ============================================================

def send_startup_alert():
    """Send a message when the daily scan starts."""
    now = datetime.now()
    send_message(
        f"🤖 <b>BHARAT EDGE STARTING</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {now.strftime('%A, %d %B %Y')}\n"
        f"🕐 {now.strftime('%H:%M IST')}\n\n"
        f"⏳ Scanning market...\n"
        f"<i>Results will follow shortly.</i>"
    )


def send_market_context_alert(market: dict):
    """Send market overview."""
    vix = market.get('vix_value', 0)
    fii = market.get('fii_net', 0)
    sgx = market.get('sgx_gap', 0)

    vix_emoji = (
        "🟢" if vix < 15 else
        "🟡" if vix < 20 else
        "🟠" if vix < 25 else
        "🔴"
    )
    vix_label = (
        "BULLISH"   if vix < 15 else
        "CAUTIOUS"  if vix < 20 else
        "DEFENSIVE" if vix < 25 else
        "BEARISH"
    )
    fii_emoji = "📈" if fii >= 0 else "📉"
    sgx_str   = f"+{sgx:.2f}%" if sgx >= 0 else f"{sgx:.2f}%"

    send_message(
        f"📊 <b>MARKET CONTEXT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{vix_emoji} VIX    : {vix:.2f} ({vix_label})\n"
        f"{fii_emoji} FII    : ₹{fii:+,.0f} Cr\n"
        f"🌏 SGX Gap: {sgx_str}\n"
    )


def send_strong_signals_alert(scan_df: pd.DataFrame) -> int:
    """
    Send alert ONLY for strong signals above threshold.
    Returns number of strong signals found.
    """
    if scan_df is None or scan_df.empty:
        send_message(
            f"😴 <b>NO SIGNALS TODAY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Market did not generate any\n"
            f"qualifying signals today.\n\n"
            f"<i>Check again tomorrow.</i>"
        )
        return 0

    # Filter only strong signals
    strong = scan_df[
        (scan_df['adj_confidence'] >= STRONG_SIGNAL_THRESHOLD) &
        (scan_df['up_votes'] >= MIN_VOTES)
    ].copy()

    if strong.empty:
        send_message(
            f"⚠️ <b>NO STRONG SIGNALS TODAY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Signals found but none above\n"
            f"{STRONG_SIGNAL_THRESHOLD}% confidence threshold.\n\n"
            f"Total scanned: {len(scan_df)} stocks\n"
            f"<i>Patience is a strategy.</i>"
        )
        return 0

    # Build strong signals message
    lines = ""
    for _, row in strong.iterrows():
        signal  = row.get('signal', '')
        conf    = row.get('adj_confidence', 0)
        votes   = row.get('up_votes', 0)
        sector  = row.get('sector', '')
        status  = row.get('sector_status', '')

        # Signal emoji
        sig_emoji = (
            "🟢🟢" if signal == 'STRONG_BUY'  else
            "🟢"   if signal == 'BUY'          else
            "🔴🔴" if signal == 'STRONG_SELL'  else
            "🔴"   if signal == 'SELL'         else
            "⚪"
        )

        # Sector status emoji
        sec_emoji = (
            "⬆️" if status == 'OVERWEIGHT'  else
            "⬇️" if status == 'UNDERWEIGHT' else
            "➡️"
        )

        lines += (
            f"\n{sig_emoji} <b>{row['symbol']}</b>\n"
            f"   Signal : {signal} ({conf:.1f}%)\n"
            f"   Votes  : {votes}/4 models agree\n"
            f"   Sector : {sector} {sec_emoji}\n"
        )

    send_message(
        f"🚨 <b>STRONG SIGNALS FOUND!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {datetime.now().strftime('%d %B %Y %H:%M IST')}\n"
        f"🎯 {len(strong)} strong signal(s) above {STRONG_SIGNAL_THRESHOLD}%\n"
        f"{lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Not financial advice. DYOR.</i>"
    )

    return len(strong)


def send_completion_alert(
        signal_count: int,
        strong_count: int,
        duration_secs: int):
    """Send scan completion summary."""
    mins = duration_secs // 60
    secs = duration_secs % 60

    # Get performance summary
    summary  = get_performance_summary()
    win_rate = summary.get('win_rate', 0)
    total    = summary.get('total_signals', 0)

    send_message(
        f"✅ <b>SCAN COMPLETE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Total Signals  : {signal_count}\n"
        f"🎯 Strong Signals : {strong_count}\n"
        f"⏱️ Duration       : {mins}m {secs}s\n\n"
        f"📈 <b>PERFORMANCE HISTORY</b>\n"
        f"   Total tracked : {total}\n"
        f"   Win Rate      : {win_rate}%\n\n"
        f"<i>Next scan: Tomorrow at 9:10 AM IST</i>"
    )


def send_weekly_summary():
    """Send weekly performance summary every Monday."""
    if datetime.now().weekday() != 0:  # 0 = Monday
        return

    if not os.path.exists("performance_history.csv"):
        return

    df       = pd.read_csv("performance_history.csv")
    summary  = get_performance_summary()
    win_rate = summary.get('win_rate', 0)
    wins     = summary.get('wins', 0)
    losses   = summary.get('losses', 0)
    pending  = summary.get('pending', 0)

    # Best signals this week
    week_df = df[df['correct'] != 'PENDING']
    best    = ""
    if not week_df.empty:
        top = week_df.nlargest(3, 'pnl_pct')
        for _, row in top.iterrows():
            best += (
                f"  {row['symbol']} "
                f"{row['signal']} "
                f"→ {row['pnl_pct']:+.1f}%\n"
            )

    send_message(
        f"📅 <b>WEEKLY SUMMARY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Week ending: "
        f"{datetime.now().strftime('%d %B %Y')}\n\n"
        f"✅ Wins    : {wins}\n"
        f"❌ Losses  : {losses}\n"
        f"⏳ Pending : {pending}\n"
        f"🎯 Win Rate: {win_rate}%\n\n"
        f"🏆 <b>Best Trades:</b>\n"
        f"{best if best else 'No completed trades yet.'}\n\n"
        f"<i>Bharat Edge AI Weekly Report</i>"
    )


# ============================================================
# MAIN - TEST
# ============================================================
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  BHARAT EDGE - TELEGRAM ALERTS TEST")
    print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
    print("="*50)

    # Load .env for local testing
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("  ✅ .env loaded")
    except Exception:
        print("  ⚠️ dotenv not available")

    # Re-read tokens after loading .env
    import importlib, sys
    TOKEN   = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

    print(f"  Token  : {'✅ Found' if TOKEN   else '❌ Missing'}")
    print(f"  ChatID : {'✅ Found' if CHAT_ID else '❌ Missing'}")

    # Test startup alert
    print("\n  Testing startup alert...")
    send_startup_alert()

    # Test market context
    print("\n  Testing market context alert...")
    send_market_context_alert({
        'vix_value': 16.5,
        'fii_net'  : 1250.0,
        'sgx_gap'  : 0.35,
    })

    # Test strong signals
    print("\n  Testing strong signals alert...")
    test_df = pd.DataFrame([{
        "symbol"        : "RELIANCE.NS",
        "signal"        : "STRONG_BUY",
        "adj_confidence": 71.8,
        "sector"        : "Energy",
        "sector_status" : "OVERWEIGHT",
        "up_votes"      : 4,
    }, {
        "symbol"        : "INFY.NS",
        "signal"        : "STRONG_BUY",
        "adj_confidence": 71.6,
        "sector"        : "IT",
        "sector_status" : "OVERWEIGHT",
        "up_votes"      : 4,
    }])
    strong_count = send_strong_signals_alert(test_df)

    # Test completion
    print("\n  Testing completion alert...")
    send_completion_alert(
        signal_count  = 6,
        strong_count  = strong_count,
        duration_secs = 187,
    )

    print("\n  ✅ All alerts tested!")
    print("  Check your Telegram for messages!")