"""Bounded automatic recovery for BharatEdge production services."""
from __future__ import annotations
import json, logging, os, shutil, subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "logs" / "health_guard.json"
HEALTH_URL = "http://127.0.0.1:8050/healthz"
RETRY_COOLDOWN = timedelta(hours=6)
MIN_FREE_DISK_PERCENT = 10.0
logger = logging.getLogger(__name__)

def _read_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError): return {}

def _write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(value) if value else None
        if parsed and parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc) if parsed else None
    except (TypeError, ValueError): return None

def recovery_allowed(last_attempt, now):
    previous = _parse_time(last_attempt)
    return previous is None or now - previous >= RETRY_COOLDOWN

def _systemctl(*args):
    return subprocess.run(["/usr/bin/systemctl", *args], check=False,
                          capture_output=True, text=True)

def _notify(message):
    try:
        from bharat_telegram import BharatTelegram
        BharatTelegram().send_message(message)
    except Exception as exc: logger.warning("Telegram health alert failed: %s", exc)

def run_guard(now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    previous = _read_json(STATE_FILE)
    issues, actions, health = [], [], {}
    try:
        with urlopen(HEALTH_URL, timeout=10) as response:
            health = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        issues.append(f"dashboard unreachable: {type(exc).__name__}")
        _systemctl("restart", "bharatedge-dashboard.service")
        actions.append("dashboard restarted")
    if health.get("scan_stalled"): issues.append("scan lifecycle marker is stalled")
    if health.get("scan_overdue"):
        issues.append("scheduled scan is overdue")
        active = _systemctl("is-active", "--quiet", "bharatedge-scan.service")
        if active.returncode != 0 and recovery_allowed(previous.get("last_scan_retry_at"), now):
            _systemctl("start", "--no-block", "bharatedge-scan.service")
            actions.append("catch-up scan requested")
            previous["last_scan_retry_at"] = now.isoformat()
    for name in ("portfolio_storage", "circuit_storage"):
        if health.get(name) in {"INVALID", "MISSING"}:
            issues.append(f"{name.replace('_', ' ')} is {health[name].lower()}")
    usage = shutil.disk_usage(ROOT)
    free_pct = usage.free / usage.total * 100 if usage.total else 0.0
    if free_pct < MIN_FREE_DISK_PERCENT: issues.append(f"disk space low ({free_pct:.1f}% free)")
    status = "UNHEALTHY" if issues else "HEALTHY"
    state = {**previous, "status": status, "checked_at": now.isoformat(),
             "issues": issues, "actions": actions,
             "disk_free_percent": round(free_pct, 1),
             "last_scan_success": health.get("last_scan_success")}
    _write_state(STATE_FILE, state)
    if status != previous.get("status"):
        _notify(f"BharatEdge health: {status}\n" + ("; ".join(issues) if issues else "all monitored checks passed"))
    logger.info("health=%s issues=%s actions=%s", status, issues, actions)
    return state

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_guard()
