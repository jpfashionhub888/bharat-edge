# retrain_and_upload.py
# Run this on your PC once a week (Sunday night)
# Trains fresh models and uploads to GitHub

import os
import sys
import pickle
import base64
import requests
from datetime import datetime

sys.path.insert(0, os.getcwd())

print("\n" + "="*55)
print("  BHARAT EDGE - WEEKLY MODEL RETRAINING")
print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
print("="*55)

# ============================================================
# YOUR GITHUB CREDENTIALS
# ============================================================

GITHUB_TOKEN = "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"
GITHUB_REPO  = "jpfashionhub888/bharat-edge"

# ============================================================

def upload_to_github(file_path, github_path):
    """Upload a file to GitHub repository."""
    try:
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()

        url     = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept"       : "application/vnd.github.v3+json",
        }

        # Check if file exists (to get SHA for update)
        resp = requests.get(url, headers=headers)
        sha  = resp.json().get("sha") if resp.status_code == 200 else None

        # Upload
        payload = {
            "message": f"Update models {datetime.now().strftime('%Y-%m-%d')}",
            "content": content,
        }
        if sha:
            payload["sha"] = sha

        resp = requests.put(url, headers=headers, json=payload)

        if resp.status_code in [200, 201]:
            print(f"  ✅ Uploaded: {github_path}")
            return True
        else:
            print(f"  ❌ Upload failed: {resp.json()}")
            return False

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def retrain_and_upload():
    """Retrain models and upload to GitHub."""

    # Step 1: Train models
    print("\n  Step 1: Training models...")
    from phase2_models import train_full_ensemble

    SYMBOLS = [
        "TCS.NS", "INFY.NS", "RELIANCE.NS",
        "HDFCBANK.NS", "ICICIBANK.NS",
        "WIPRO.NS", "SBIN.NS", "BAJFINANCE.NS",
    ]

    ensemble = train_full_ensemble(
        symbols     = SYMBOLS,
        period      = "2y",
        save_models = True,
        vix_value   = 17.21,
        vix_change  = -4.9,
        fii_net     = 500,
        dii_net     = 300,
        sgx_gap     = 0.65,
    )

    if not ensemble:
        print("  ❌ Training failed!")
        return False

    print(f"\n  ✅ Training complete!")
    print(f"     Accuracy: {ensemble['voting_acc']*100:.1f}%")
    print(f"     Samples : {ensemble['training_samples']}")

    # Step 2: Upload models to GitHub
    print("\n  Step 2: Uploading models to GitHub...")

    model_files = [
        "models/xgboost.pkl",
        "models/lightgbm.pkl",
        "models/random_forest.pkl",
        "models/extra_trees.pkl",
        "models/scaler.pkl",
        "models/feature_names.pkl",
    ]

    success = 0
    for file_path in model_files:
        if os.path.exists(file_path):
            github_path = file_path.replace("\\", "/")
            if upload_to_github(file_path, github_path):
                success += 1
        else:
            print(f"  ⚠️ Not found: {file_path}")

    print(f"\n  ✅ Uploaded {success}/{len(model_files)} models")
    return success > 0


if __name__ == "__main__":
    success = retrain_and_upload()

    if success:
        print(f"\n{'='*55}")
        print(f"  ✅ RETRAINING COMPLETE!")
        print(f"  Models uploaded to GitHub")
        print(f"  GitHub Actions will use these tomorrow")
        print(f"{'='*55}")
    else:
        print(f"\n  ❌ Retraining failed!")