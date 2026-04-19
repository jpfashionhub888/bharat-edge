# phase6_telegram.py
# BHARAT EDGE - Telegram Bot
# Sends daily report + signals automatically

import warnings
warnings.filterwarnings('ignore')
import os
import sys
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# ============================================================
# 🔐 YOUR CREDENTIALS
# ============================================================

BOT_TOKEN = os.environ.get('8543146915:AAHGLpUz7IPyWDzSEAqjxV1zb_ZReGj9VsA', '')
CHAT_ID   =  os.environ.get('8616636381', '')

# ============================================================

BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ============================================================
# SECTION 1: CORE SENDER FUNCTIONS
# ============================================================

def send_message(text: str) -> dict:
    """Send plain text or HTML message."""
    try:
        url     = f"{BASE_URL}/sendMessage"
        payload = {
            "chat_id"   : CHAT_ID,
            "text"      : text,
            "parse_mode": "HTML",
        }
        response = requests.post(url, data=payload, timeout=10)
        result   = response.json()
        if result.get('ok'):
            print(f"  ✅ Message sent ({len(text)} chars)")
        else:
            print(f"  ❌ Send failed: {result}")
        return result
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {}


def send_long_message(text: str) -> None:
    """
    Send long message by splitting into chunks.
    Telegram limit is 4096 chars per message.
    """
    max_len = 4000
    chunks  = [text[i:i+max_len]
               for i in range(0, len(text), max_len)]
    for i, chunk in enumerate(chunks, 1):
        print(f"  Sending chunk {i}/{len(chunks)}...")
        send_message(f"<pre>{chunk}</pre>")


def send_file(file_path: str) -> dict:
    """Send a file (CSV, PDF etc) to Telegram."""
    try:
        if not os.path.exists(file_path):
            print(f"  ❌ File not found: {file_path}")
            return {}

        url = f"{BASE_URL}/sendDocument"
        with open(file_path, "rb") as f:
            files    = {"document": f}
            payload  = {"chat_id": CHAT_ID}
            response = requests.post(
                url, files=files,
                data=payload, timeout=30)
        result = response.json()
        if result.get('ok'):
            print(f"  ✅ File sent: {file_path}")
        else:
            print(f"  ❌ File send failed: {result}")
        return result
    except Exception as e:
        print(f"  ❌ File error: {e}")
        return {}


# ============================================================
# SECTION 2: REPORT SENDERS
# ============================================================

def send_test_message() -> None:
    """Send a simple test message."""
    now = datetime.now().strftime("%d %b %Y %H:%M:%S")
    msg = (
        f"<b>BHARAT EDGE BOT CONNECTED!</b>\n\n"
        f"Time: {now}\n"
        f"Status: Online\n"
        f"System: Ready"
    )
    send_message(msg)


def send_daily_report() -> None:
    """Send the daily_report.txt to Telegram."""
    report_path = "daily_report.txt"

    if not os.path.exists(report_path):
        send_message(
            "No daily report found.\n"
            "Run phase3_scanner.py first!"
        )
        return

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report = f.read()

        print(f"  Report length: {len(report)} chars")
        send_long_message(report)

    except Exception as e:
        print(f"  ❌ Report error: {e}")
        send_message(f"Error reading report: {e}")


def send_scan_results() -> None:
    """Send latest scan CSV file."""
    # Find latest scan file
    scan_files = [
        f for f in os.listdir('.')
        if f.startswith("scan_") and f.endswith(".csv")
    ]

    if not scan_files:
        send_message("No scan files found!")
        return

    latest = sorted(scan_files)[-1]
    print(f"  Sending scan file: {latest}")
    send_file(latest)


def send_signal_alert(signals_df) -> None:
    """
    Send formatted signal alert from scan results.
    Called directly from scanner.
    """
    if signals_df is None or signals_df.empty:
        send_message(
            "<b>BHARAT EDGE SCAN COMPLETE</b>\n\n"
            "No signals today.\n"
            f"Time: {datetime.now().strftime('%H:%M')}"
        )
        return

    now      = datetime.now().strftime("%d %b %Y %H:%M")
    date_str = datetime.now().strftime("%A, %d %B %Y")

    # Build signal lines
    signal_lines = ""
    for i, row in signals_df.head(5).iterrows():
        status = row.get('sector_status', '')
        tag    = ("OW" if status == 'OVERWEIGHT'
                  else "N" if status == 'NEUTRAL'
                  else "UW")
        conf   = row.get('adj_confidence', 0)
        sig    = row.get('signal', '')
        sym    = row.get('symbol', '')
        sect   = row.get('sector', '')
        votes  = row.get('up_votes', 0)

        signal_lines += (
            f"\n  {sym}"
            f"\n  Signal: {sig} ({conf:.1f}%)"
            f"\n  Sector: {sect} [{tag}]"
            f"\n  Votes : {votes}/4 models"
            f"\n"
        )

    msg = (
        f"<b>BHARAT EDGE - DAILY SCAN</b>\n"
        f"<b>{date_str}</b>\n"
        f"{'─'*30}\n\n"
        f"<b>MARKET:</b>\n"
        # ✅ NEW - pass market as parameter
        f"<b>TOP SIGNALS:</b>"
        f"{signal_lines}\n"
        f"<b>SUMMARY:</b>\n"
        f"  Total Signals : {len(signals_df)}\n"
        f"  Avg Confidence: "
        f"{signals_df['adj_confidence'].mean():.1f}%\n\n"
        f"<i>Bharat Edge AI - {now}</i>"
    )

    send_message(msg)


def send_morning_report() -> None:
    """
    Send complete morning report.
    Runs sector rotation + scan + sends everything.
    """
    print("\n  Generating morning report...")

    # Send header first
    send_message(
        f"<b>BHARAT EDGE MORNING REPORT</b>\n"
        f"{datetime.now().strftime('%A, %d %B %Y')}\n"
        f"Generating scan... please wait."
    )

    # Run sector rotation
    try:
        from phase3_sector import run_sector_rotation

        rotation = run_sector_rotation(
            vix_value = 17.21,
            fii_net   = 500,
            verbose   = False,
        )

        if not rotation.empty:
            ow = rotation[
                rotation['status'] == 'OVERWEIGHT'
            ]['sector'].tolist()
            uw = rotation[
                rotation['status'] == 'UNDERWEIGHT'
            ]['sector'].tolist()

            rotation_msg = (
                f"<b>SECTOR ROTATION</b>\n"
                f"{'─'*30}\n"
                f"BUY   : {', '.join(ow)}\n"
                f"AVOID : {', '.join(uw)}\n\n"
                f"<b>SECTOR SCORES:</b>\n"
            )

            for _, row in rotation.iterrows():
                tag = (
                    "[OW]" if row['status'] == 'OVERWEIGHT'
                    else "[N] " if row['status'] == 'NEUTRAL'
                    else "[UW]"
                )
                rotation_msg += (
                    f"  {tag} {row['sector']:<12} "
                    f"Score={row['score']:.1f}  "
                    f"1M={row['mom_1m']:+.1f}%\n"
                )

            send_message(f"<pre>{rotation_msg}</pre>")

    except Exception as e:
        print(f"  Rotation error: {e}")

    # Run scanner
    try:
        from phase2_models import load_all_models
        from phase3_scanner import run_full_scan

        ensemble = load_all_models()
        if ensemble:
            # ✅ NEW
            from phase6_market_data import get_live_market_context
            MARKET, SNAPSHOT = get_live_market_context()

            scan_df = run_full_scan(
                ensemble = ensemble,
                verbose  = False,
                **MARKET,
            )

            # Send signal alert
            send_signal_alert(scan_df)

            # Send CSV file
            if scan_df is not None and not scan_df.empty:
                scan_files = sorted([
                    f for f in os.listdir('.')
                    if f.startswith("scan_")
                    and f.endswith(".csv")
                ])
                if scan_files:
                    send_file(scan_files[-1])

    except Exception as e:
        print(f"  Scanner error: {e}")
        send_message(f"Scanner error: {e}")

    send_message(
        f"<b>Morning report complete!</b>\n"
        f"Time: {datetime.now().strftime('%H:%M:%S')}"
    )


def send_evening_report() -> None:
    """Send evening P&L summary."""
    trade_log = "trade_log_v2.csv"

    if not os.path.exists(trade_log):
        send_message("No trade log found!")
        return

    try:
        import pandas as pd
        df = pd.read_csv(trade_log)

        total     = len(df)
        wins      = (df['pnl'] > 0).sum()
        win_rate  = wins / total * 100
        total_pnl = df['pnl'].sum()
        today_df  = df[
            df['exit_date'].str.startswith(
                datetime.now().strftime('%Y-%m-%d'),
                na=False
            )
        ] if 'exit_date' in df.columns else pd.DataFrame()

        today_pnl = today_df['pnl'].sum() if not today_df.empty else 0

        msg = (
            f"<b>BHARAT EDGE EVENING REPORT</b>\n"
            f"{datetime.now().strftime('%A, %d %B %Y')}\n"
            f"{'─'*30}\n\n"
            f"<b>TODAY:</b>\n"
            f"  Trades  : {len(today_df)}\n"
            f"  P&L     : Rs {today_pnl:+,.0f}\n\n"
            f"<b>OVERALL:</b>\n"
            f"  Total Trades : {total}\n"
            f"  Win Rate     : {win_rate:.1f}%\n"
            f"  Total P&L    : Rs {total_pnl:+,.0f}\n\n"
            f"<i>Bharat Edge AI - "
            f"{datetime.now().strftime('%H:%M')}</i>"
        )
        send_message(msg)

    except Exception as e:
        send_message(f"Evening report error: {e}")


# ============================================================
# SECTION 3: SCHEDULED AUTOMATION
# ============================================================

def run_automation():
    """
    Run automated daily tasks.
    Call this from scheduler or cloud.
    """
    hour = datetime.now().hour

    print(f"\n  Running automation for hour: {hour}")

    if hour == 9:
        # 9 AM - Morning report
        print("  Running morning report...")
        send_morning_report()

    elif hour == 15:
        # 3 PM - Evening report
        print("  Running evening report...")
        send_evening_report()

    else:
        # Manual run
        print("  Running manual scan...")
        send_morning_report()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  BHARAT EDGE - TELEGRAM BOT")
    print("="*50)

    print("\n  What do you want to send?")
    print("  1. Test message only")
    print("  2. Daily report (text)")
    print("  3. Full morning report (scan + signals)")
    print("  4. Evening P&L report")
    print("  5. Send all")

    choice = input("\n  Enter choice (1-5): ").strip()

    if choice == "1":
        print("\n  Sending test message...")
        send_test_message()

    elif choice == "2":
        print("\n  Sending daily report...")
        send_daily_report()

    elif choice == "3":
        print("\n  Sending full morning report...")
        send_morning_report()

    elif choice == "4":
        print("\n  Sending evening report...")
        send_evening_report()

    elif choice == "5":
        print("\n  Sending everything...")
        send_test_message()
        send_daily_report()
        send_morning_report()

    else:
        print("\n  Invalid choice!")
        print("  Sending test message by default...")
        send_test_message()

    print("\n" + "="*50)
    print("  DONE!")
    print("="*50)