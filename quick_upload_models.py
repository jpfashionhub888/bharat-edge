# quick_upload_models.py
# Just uploads existing models to GitHub (no retraining)

import os
import sys
import base64
import requests
from datetime import datetime

# ============================================================
# YOUR GITHUB CREDENTIALS
# ============================================================

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO  = "jpfashionhub888/bharat-edge"

# ============================================================

def upload_file(local_path, github_path):
    """Upload one file to GitHub."""
    try:
        if not os.path.exists(local_path):
            print(f"  ❌ Not found: {local_path}")
            return False

        with open(local_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()

        url     = (f"https://api.github.com/repos/"
                   f"{GITHUB_REPO}/contents/{github_path}")
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept"       : "application/vnd.github.v3+json",
        }

        # Check if file exists (need SHA to update)
        resp = requests.get(url, headers=headers, timeout=15)
        sha  = None
        if resp.status_code == 200:
            sha = resp.json().get("sha")

        # Upload
        payload = {
            "message": (f"Update models "
                        f"{datetime.now().strftime('%Y-%m-%d')}"),
            "content": content,
        }
        if sha:
            payload["sha"] = sha

        resp = requests.put(
            url, headers=headers,
            json=payload, timeout=30)

        if resp.status_code in [200, 201]:
            size = os.path.getsize(local_path) / 1024
            print(f"  ✅ {github_path} ({size:.0f} KB)")
            return True
        else:
            print(f"  ❌ Failed: {resp.json().get('message')}")
            return False

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*55)
    print("  BHARAT EDGE - UPLOAD MODELS TO GITHUB")
    print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
    print("="*55)

    # Check token
    if "PASTE" in GITHUB_TOKEN:
        print("\n  ❌ Please add your GitHub token first!")
        print("  Get it from: https://github.com/settings/tokens")
        exit(1)

    # Test token first
    print("\n  Testing GitHub connection...")
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept"       : "application/vnd.github.v3+json",
    }
    test = requests.get(
        "https://api.github.com/user",
        headers=headers, timeout=10)

    if test.status_code == 200:
        username = test.json().get('login', 'unknown')
        print(f"  ✅ Connected as: {username}")
    else:
        print(f"  ❌ Token invalid! Status: {test.status_code}")
        print(f"  Create new token at: "
              f"https://github.com/settings/tokens")
        exit(1)

    # Upload models
    print("\n  Uploading models...")

    model_files = [
        ("models/xgboost.pkl",       "models/xgboost.pkl"),
        ("models/lightgbm.pkl",      "models/lightgbm.pkl"),
        ("models/random_forest.pkl", "models/random_forest.pkl"),
        ("models/extra_trees.pkl",   "models/extra_trees.pkl"),
        ("models/scaler.pkl",        "models/scaler.pkl"),
        ("models/feature_names.pkl", "models/feature_names.pkl"),
    ]

    success = 0
    for local_path, github_path in model_files:
        if upload_file(local_path, github_path):
            success += 1
        import time
        time.sleep(1)  # Be nice to GitHub API

    print(f"\n  {'='*40}")
    if success == len(model_files):
        print(f"  ✅ ALL {success} models uploaded!")
        print(f"  GitHub Actions will use these models")
        print(f"  next time it runs!")
    else:
        print(f"  ⚠️ {success}/{len(model_files)} uploaded")

    print(f"  {'='*40}")
    print(f"\n  View at:")
    print(f"  https://github.com/{GITHUB_REPO}/tree/main/models")