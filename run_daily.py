# run_daily.py
# BHARAT EDGE - Daily Automation
# Downloads pre-trained models from GitHub
# Then runs scan + sends Telegram

import warnings
warnings.filterwarnings('ignore')
import os
import sys
import time
import pickle
import base64
import requests

os.environ['LOKY_MAX_CPU_COUNT'] = '1'
os.environ['PYTHONWARNINGS']     = 'ignore'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from datetime import datetime
import pandas as pd
import numpy as np

print("\n" + "="*55)
print("  BHARAT EDGE - DAILY AUTOMATION")
print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M IST')}")
print("="*55)

# ============================================================
# CREDENTIALS
# ============================================================

TOKEN        = os.environ.get('8543146915:AAHGLpUz7IPyWDzSEAqjxV1zb_ZReGj9VsA', '')
CHAT_ID      = os.environ.get('8616636381', '')
GITHUB_TOKEN = os.environ.get('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', '')
GITHUB_REPO  = "jpfashionhub888/bharat-edge"


# ============================================================
# TELEGRAM
# ============================================================

def send_msg(text: str) -> bool:
    if not TOKEN or not CHAT_ID:
        print(f"  [MSG] {text[:60]}")
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
            print(f"  ✅ Sent: {text[:40]}...")
        return ok
    except Exception as e:
        print(f"  ❌ Telegram: {e}")
        return False


def send_file(path: str) -> bool:
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
        print(f"  ❌ File: {e}")
        return False


# ============================================================
# SECTION 1: DOWNLOAD MODELS FROM GITHUB
# ============================================================

def models_exist_locally() -> bool:
    """Check if all models already exist in the models/ folder."""
    required = [
        "models/xgboost.pkl",
        "models/lightgbm.pkl",
        "models/random_forest.pkl",
        "models/extra_trees.pkl",
        "models/scaler.pkl",
        "models/feature_names.pkl",
    ]
    missing = [m for m in required if not os.path.exists(m)]
    if missing:
        print(f"  ⚠️ Missing models: {missing}")
        return False
    print("  ✅ All models found locally. Skipping download.")
    return True


def download_models_from_github() -> bool:
    """
    Download pre-trained models from GitHub repository.
    Models were uploaded by retrain_and_upload.py
    """
    print("\n  Downloading models from GitHub...")

    os.makedirs("models", exist_ok=True)

    model_files = [
        "models/xgboost.pkl",
        "models/lightgbm.pkl",
        "models/random_forest.pkl",
        "models/extra_trees.pkl",
        "models/scaler.pkl",
        "models/feature_names.pkl",
    ]

    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    headers["Accept"] = "application/vnd.github.v3+json"

    success = 0
    for github_path in model_files:
        try:
            url  = (f"https://api.github.com/repos/"
                    f"{GITHUB_REPO}/contents/{github_path}")
            resp = requests.get(url, headers=headers, timeout=30)

            if resp.status_code == 200:
                data    = resp.json()
                content = base64.b64decode(data['content'])

                local_path = github_path.replace("/", os.sep)
                os.makedirs(os.path.dirname(
                    local_path), exist_ok=True)

                with open(local_path, "wb") as f:
                    f.write(content)

                print(f"  ✅ Downloaded: {github_path}")
                success += 1
            else:
                print(f"  ❌ Not found: {github_path} "
                      f"(status={resp.status_code})")

        except Exception as e:
            print(f"  ❌ Download error {github_path}: {e}")

    print(f"\n  Downloaded {success}/{len(model_files)} models")
    return success >= 4  # Need at least 4 base models


# ============================================================
# SECTION 2: LOAD MODELS
# ============================================================

def load_models() -> dict:
    """Load downloaded models."""
    print("\n  Loading models...")
    try:
        from phase2_models import load_all_models
        ensemble = load_all_models()
        if ensemble:
            print(f"  ✅ Models loaded: "
                  f"{list(ensemble['base_models'].keys())}")
            return ensemble
        else:
            print("  ❌ Failed to load models!")
            return {}
    except Exception as e:
        print(f"  ❌ Load error: {e}")
        return {}


# ============================================================
# SECTION 3: FETCH LIVE DATA (Small requests only)
# ============================================================

def get_market_context() -> dict:
    """Get live market context."""
    print("\n  Fetching live market context...")

    try:
        time.sleep(3)
        from phase6_market_data import get_live_market_context
        context, snapshot = get_live_market_context()
        print(f"  ✅ VIX={context['vix_value']:.1f} "
              f"SGX={context['sgx_gap']:+.2f}%")
        return context
    except Exception as e:
        print(f"  ⚠️ Live context failed: {e}")
        return dict(
            vix_value=17.0, vix_change=0.0,
            fii_net=0.0, dii_net=0.0,
            sgx_gap=0.0, news_sentiment=0.0,
            news_volume=0,
        )


# ============================================================
# SECTION 4: RUN SCAN
# ============================================================

def run_scan(ensemble, market) -> pd.DataFrame:
    """Run portfolio scan using downloaded models."""
    print("\n  Running portfolio scan...")

    try:
        time.sleep(2)
        from phase3_scanner import run_full_scan

        scan_df = run_full_scan(
            ensemble = ensemble,
            verbose  = True,
            **market,
        )
        return scan_df if scan_df is not None else pd.DataFrame()

    except Exception as e:
        print(f"  ❌ Scan error: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


# ============================================================
# SECTION 5: SEND REPORTS
# ============================================================

def send_reports(scan_df, market):
    """Send all reports to Telegram."""
    vix = market.get('vix_value', 0)
    fii = market.get('fii_net', 0)
    sgx = market.get('sgx_gap', 0)

    vix_label = (
        "BULLISH"   if vix < 15 else
        "CAUTIOUS"  if vix < 20 else
        "DEFENSIVE" if vix < 25 else
        "BEARISH"
    )
    fii_label = "BUYING" if fii >= 0 else "SELLING"
    sgx_str   = f"+{sgx:.2f}%" if sgx >= 0 else f"{sgx:.2f}%"
    date_str  = datetime.now().strftime("%A, %d %B %Y")
    time_str  = datetime.now().strftime("%H:%M IST")

    # Sector rotation report
    try:
        time.sleep(2)
        from phase3_sector import run_sector_rotation
        rotation = run_sector_rotation(
            vix_value=vix, fii_net=fii, verbose=False)

        if not rotation.empty:
            ow = rotation[
                rotation['status']=='OVERWEIGHT'
            ]['sector'].tolist()
            uw = rotation[
                rotation['status']=='UNDERWEIGHT'
            ]['sector'].tolist()

            scores = ""
            for _, row in rotation.iterrows():
                tag = (
                    "[OW]" if row['status']=='OVERWEIGHT'
                    else "[N] " if row['status']=='NEUTRAL'
                    else "[UW]"
                )
                scores += (
                    f"{tag} {row['sector']:<12} "
                    f"{row['score']:.0f}  "
                    f"1M={row['mom_1m']:+.1f}%\n"
                )

            send_msg(
                f"<b>BHARAT EDGE</b>\n"
                f"<b>{date_str} {time_str}</b>\n"
                f"{'─'*30}\n\n"
                f"<b>MARKET:</b>\n"
                f"  VIX : {vix:.2f} ({vix_label})\n"
                f"  FII : Rs {fii:+,.0f} Cr ({fii_label})\n"
                f"  SGX : {sgx_str}\n\n"
                f"<b>BUY SECTORS:</b> {', '.join(ow)}\n"
                f"<b>AVOID:</b> {', '.join(uw)}\n\n"
                f"<b>SCORES:</b>\n<pre>{scores}</pre>"
            )
            time.sleep(3)

    except Exception as e:
        print(f"  ⚠️ Rotation error: {e}")

    # Signals report
    if scan_df is not None and not scan_df.empty:
        lines = ""
        for i, row in scan_df.head(5).iterrows():
            status = row.get('sector_status', '')
            tag    = ("OW" if status=='OVERWEIGHT'
                      else "N" if status=='NEUTRAL'
                      else "UW")
            lines += (
                f"\n  {row['symbol']}\n"
                f"  {row['signal']} "
                f"({row['adj_confidence']:.1f}%) [{tag}]\n"
                f"  Votes: {row.get('up_votes',0)}/4\n"
            )

        send_msg(
            f"<b>TOP SIGNALS:</b>"
            f"{lines}\n"
            f"Total: {len(scan_df)} | "
            f"Avg: {scan_df['adj_confidence'].mean():.1f}%\n\n"
            f"<i>Bharat Edge AI - {time_str}</i>"
        )

        # Send CSV
        csv_files = sorted([
            f for f in os.listdir('.')
            if f.startswith("scan_") and f.endswith(".csv")
        ])
        if csv_files:
            time.sleep(2)
            send_file(csv_files[-1])

    else:
        send_msg(
            f"<b>BHARAT EDGE - {date_str}</b>\n\n"
            f"No signals today.\n"
            f"VIX: {vix:.2f} ({vix_label})\n\n"
            f"<i>{time_str}</i>"
        )

    if os.path.exists("daily_report.txt"):
        time.sleep(2)
        send_file("daily_report.txt")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    start = datetime.now()

    send_msg(
        f"<b>BHARAT EDGE STARTING</b>\n"
        f"{datetime.now().strftime('%d %b %Y %H:%M IST')}\n"
        f"Checking models..."
    )

    # Step 1: Check if models exist locally, if not download from GitHub
    if models_exist_locally():
        print("  ✅ Using local models.")
        downloaded = True
    else:
        print("  ⬇️ Models not found locally. Downloading from GitHub...")
        downloaded = download_models_from_github()

    if not downloaded:
        send_msg(
            "❌ <b>Model download failed!</b>\n"
            "Run retrain_and_upload.py on your PC\n"
            "to upload fresh models to GitHub"
        )
        exit(1)

    # Step 2: Load models
    ensemble = load_models()
    if not ensemble:
        send_msg("❌ Could not load models!")
        exit(1)

    # Step 3: Market context
    market = get_market_context()

    # Step 4: Run scan
    scan_df = run_scan(ensemble, market)

    # Step 5: Send reports
    send_reports(scan_df, market)

    # Step 6: Save results to CSV for GitHub commit
    if scan_df is not None and not scan_df.empty:
        scan_df.to_csv("latest_results.csv", index=False)
        print("  ✅ Results saved to latest_results.csv")
    else:
        pd.DataFrame({"date": [datetime.now().strftime('%Y-%m-%d')],
                      "signals": [0],
                      "status": ["No signals today"]
                      }).to_csv("latest_results.csv", index=False)
        print("  ✅ Empty results saved to latest_results.csv")

    # Done
    duration     = (datetime.now() - start).seconds
    signal_count = len(scan_df) if scan_df is not None else 0

    send_msg(
        f"✅ <b>BHARAT EDGE COMPLETE</b>\n\n"
        f"Signals  : {signal_count}\n"
        f"Duration : {duration//60}m {duration%60}s\n"
        f"Time     : {datetime.now().strftime('%H:%M IST')}\n\n"
        f"<i>Next run: Tomorrow 9:10 AM IST</i>"
    )

    print(f"\n{'='*55}")
    print(f"  COMPLETE!")
    print(f"  Duration: {duration//60}m {duration%60}s")
    print(f"  Signals : {signal_count}")
    print(f"{'='*55}")