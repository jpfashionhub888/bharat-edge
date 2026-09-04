# bharat_model_cache.py
# BHARATEDGE - Model Cache System
# Retrains models every 30 days automatically

import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

CACHE_INFO_FILE = 'models/bharat_cache_info.json'
RETRAIN_DAYS    = 30


def load_cache_info():
    if not os.path.exists(CACHE_INFO_FILE):
        return {}
    try:
        with open(CACHE_INFO_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache_info(info):
    os.makedirs('models', exist_ok=True)
    tmp_file = CACHE_INFO_FILE + '.tmp'
    with open(tmp_file, 'w') as f:
        json.dump(info, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, CACHE_INFO_FILE)


def should_retrain():
    """Check if models need retraining."""
    info = load_cache_info()

    if 'last_trained' not in info:
        print("   No cache info found - need to train!")
        return True

    try:
        last_trained = datetime.fromisoformat(info['last_trained'])
        expiry_days = int(info.get('retrain_days', RETRAIN_DAYS))
        if expiry_days < 1 or expiry_days > 365:
            raise ValueError('retrain_days outside safe range')
        days_since = (datetime.now() - last_trained).days
        if days_since < -1:
            raise ValueError('last_trained is unexpectedly in the future')
    except (TypeError, ValueError, OverflowError) as exc:
        logger.warning('Invalid model cache metadata; retraining required: %s', exc)
        return True

    print(f"   Models trained: {last_trained.strftime('%Y-%m-%d')}")
    print(f"   Days since training: {days_since}")
    print(f"   Retrain interval: {expiry_days} days")

    if days_since >= expiry_days:
        print(f"   Cache EXPIRED - retraining needed!")
        return True

    print(f"   Cache VALID - {expiry_days - days_since} days until retrain")
    return False


def mark_trained():
    """Mark models as freshly trained."""
    info = {
        'last_trained' : datetime.now().isoformat(),
        'retrain_days' : RETRAIN_DAYS,
        'expires_at'   : (
            datetime.now() + timedelta(days=RETRAIN_DAYS)
        ).isoformat(),
    }
    save_cache_info(info)
    print(f"   Models marked as trained on {datetime.now().strftime('%Y-%m-%d')}")


def get_cache_status():
    """Print cache status."""
    info = load_cache_info()
    if not info:
        print("   No cache found - models need training")
        return

    print(f"\n   BHARAT MODEL CACHE STATUS:")
    print(f"   Last trained: {info.get('last_trained', 'Never')[:10]}")
    print(f"   Expires at:   {info.get('expires_at', 'Unknown')[:10]}")
    needs = should_retrain()
    print(f"   Needs retrain: {needs}")


if __name__ == '__main__':
    get_cache_status()
