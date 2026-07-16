# -*- coding: utf-8 -*-
# audit_bharat.py
"""
BharatEdge Deep Audit

Checks system health before/after each deployment or on demand.

Checks:
  1. Required env vars present
  2. Telegram connection live (getMe)
  3. Circuit breaker state
  4. Trade tracker health & stats
  5. Model freshness (saved_models/)
  6. .env not committed to git
  7. Bot control state (paused?)
  8. logs/ directory writeable
  9. command_listener imports OK
  10. trade_tracker imports OK

Usage:
  python audit_bharat.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# -- Helpers -----------------------------------------------------------

PASS = '  [OK]'
FAIL = '  [FAIL]'
WARN = '  [WARN]'

results = []

def check(name: str, ok: bool, detail: str = '') -> bool:
    flag = PASS if ok else FAIL
    line = f'{flag}  {name}'
    if detail:
        line += f'  --  {detail}'
    print(line)
    results.append({'name': name, 'ok': ok, 'detail': detail})
    return ok


# -- 1. Required env vars ----------------------------------------------

def check_env_vars():
    print('\n-- Environment Variables --------------------------------')
    required = [
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_CHAT_ID',
        'GITHUB_TOKEN',
    ]
    optional = [
        'KITE_API_KEY',
        'KITE_API_SECRET',
        'KITE_USER_ID',
        'GROQ_API_KEY',
    ]
    all_ok = True
    for var in required:
        val = os.getenv(var, '')
        ok  = bool(val) and 'YOUR_' not in val
        check(f'${var}', ok, f'(set)' if ok else 'MISSING or placeholder')
        all_ok = all_ok and ok

    for var in optional:
        val = os.getenv(var, '')
        ok  = bool(val)
        flag = PASS if ok else WARN
        print(f'{flag}  ${var}  --  {"set" if ok else "not set (optional)"}')
    return all_ok


# -- 2. Telegram connection --------------------------------------------

def check_telegram():
    print('\n-- Telegram Connection ----------------------------------')
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    if not token:
        check('Telegram getMe', False, 'No token set')
        return False
    if not _HAS_REQUESTS:
        check('Telegram getMe', False, 'requests not installed')
        return False
    try:
        resp = requests.get(
            f'https://api.telegram.org/bot{token}/getMe',
            timeout=10
        )
        data = resp.json()
        if data.get('ok'):
            bot = data['result']
            return check(
                'Telegram getMe',
                True,
                f"@{bot.get('username')} ({bot.get('first_name')})"
            )
        else:
            return check('Telegram getMe', False, str(data.get('description', 'Unknown error')))
    except Exception as e:
        return check('Telegram getMe', False, str(e))


# -- 3. Circuit breaker ------------------------------------------------

def check_circuit_breaker():
    print('\n-- Circuit Breaker --------------------------------------')
    cb_file = 'logs/circuit_breaker.json'
    if not os.path.exists(cb_file):
        print(f'{WARN}  circuit_breaker.json  --  not found (will be created on first scan)')
        return True
    try:
        with open(cb_file) as f:
            cb = json.load(f)
        triggered = cb.get('triggered', False)
        reason    = cb.get('trigger_reason', '')
        ok = not triggered
        detail = 'Clear' if ok else f'TRIGGERED: {reason}'
        return check('Circuit breaker', ok, detail)
    except Exception as e:
        return check('Circuit breaker', False, str(e))


# -- 4. Trade tracker --------------------------------------------------

def check_trade_tracker():
    print('\n-- Trade Tracker ----------------------------------------')
    trades_file = 'logs/closed_trades.json'

    # Import check
    try:
        sys.path.insert(0, os.getcwd())
        from monitoring.trade_tracker import get_trade_stats
        check('monitoring.trade_tracker import', True)
    except ImportError as e:
        check('monitoring.trade_tracker import', False, str(e))
        return False

    if not os.path.exists(trades_file):
        print(f'{WARN}  {trades_file}  --  not found (created on first closed trade)')
        return True

    try:
        stats = get_trade_stats(trades_file)
        total = stats.get('total', 0)
        wr    = stats.get('win_rate', 0) * 100
        pnl   = stats.get('total_pnl', 0)
        pf    = stats.get('profit_factor') or 0
        check('Trade file readable', True, f'{total} trades, wr={wr:.1f}%, P&L=₹{pnl:+,.2f}, PF={pf:.2f}')
        return True
    except Exception as e:
        return check('Trade file readable', False, str(e))


# -- 5. Model freshness ------------------------------------------------

def check_model_freshness():
    print('\n-- Model Freshness --------------------------------------')
    models_dir = 'saved_models'
    pkl_files  = list(Path(models_dir).glob('*.pkl')) if Path(models_dir).exists() else []

    if not pkl_files:
        print(f'{WARN}  Models  --  no .pkl files found in {models_dir}/')
        return True

    newest = max(pkl_files, key=lambda p: p.stat().st_mtime)
    age    = (datetime.now() - datetime.fromtimestamp(newest.stat().st_mtime)).days
    ok     = age < 7
    return check('Model freshness', ok, f'{newest.name} is {age}d old {"✓" if ok else "(STALE -- retrain needed)"}')


# -- 6. .env not committed ---------------------------------------------

def check_env_not_committed():
    print('\n-- Git Security -----------------------------------------')
    try:
        result = subprocess.run(
            ['git', 'ls-files', '.env'],
            capture_output=True, text=True, cwd='.'
        )
        committed = bool(result.stdout.strip())
        return check('.env not in git', not committed,
                     'DANGER: .env is tracked by git!' if committed else 'Safe')
    except Exception as e:
        print(f'{WARN}  Could not check git: {e}')
        return True


# -- 7. Bot control state ----------------------------------------------

def check_bot_control():
    print('\n-- Bot Control State ------------------------------------')
    ctrl_file = 'logs/bot_control.json'
    if not os.path.exists(ctrl_file):
        print(f'{WARN}  bot_control.json  --  not found (created on first command)')
        return True
    try:
        with open(ctrl_file) as f:
            ctrl = json.load(f)
        paused = ctrl.get('paused', False)
        reason = ctrl.get('reason', '')
        ok     = not paused
        detail = 'Running' if ok else f'PAUSED: {reason}'
        return check('Bot control', ok, detail)
    except Exception as e:
        return check('Bot control', False, str(e))


# -- 8. Logs directory writable ----------------------------------------

def check_logs_dir():
    print('\n-- Filesystem -------------------------------------------')
    os.makedirs('logs', exist_ok=True)
    test_file = 'logs/.audit_write_test'
    try:
        with open(test_file, 'w') as f:
            f.write('ok')
        os.remove(test_file)
        return check('logs/ writable', True)
    except Exception as e:
        return check('logs/ writable', False, str(e))


# -- 9 & 10. Module imports --------------------------------------------

def check_imports():
    print('\n-- Module Imports ---------------------------------------')
    modules = [
        ('monitoring.command_listener', 'start_command_listener'),
        ('monitoring.trade_tracker',    'TradeTracker'),
        ('monitoring.model_watchdog',   'run_watchdog_report'),
        ('bharat_telegram',             'BharatTelegram'),
        ('bharat_paper_trader',         'BharatPaperTrader'),
        ('risk_circuit_breaker',        'RiskCircuitBreaker'),
    ]
    all_ok = True
    for module, attr in modules:
        try:
            mod = __import__(module, fromlist=[attr])
            getattr(mod, attr)
            check(f'{module}.{attr}', True)
        except Exception as e:
            check(f'{module}.{attr}', False, str(e))
            all_ok = False
    return all_ok


# -- Main --------------------------------------------------------------

def main():
    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    print('\n' + '=' * 55)
    print('  BHARATEDGE DEEP AUDIT')
    print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M IST')}")
    print('=' * 55)

    check_env_vars()
    check_telegram()
    check_circuit_breaker()
    check_trade_tracker()
    check_model_freshness()
    check_env_not_committed()
    check_bot_control()
    check_logs_dir()
    check_imports()

    # Summary
    total    = len(results)
    passed   = sum(1 for r in results if r['ok'])
    failed   = total - passed
    failures = [r for r in results if not r['ok']]

    print('\n' + '=' * 55)
    print(f'  AUDIT RESULT: {passed}/{total} checks passed')
    if failures:
        print(f'  FAILURES ({failed}):')
        for r in failures:
            print(f'    [FAIL] {r["name"]}  --  {r["detail"]}')
    else:
        print('  [OK] All checks passed -- BharatEdge is healthy!')
    print('=' * 55 + '\n')

    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
