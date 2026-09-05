# risk_circuit_breaker.py
# ALPHAEDGE - Risk Circuit Breaker
# Stops trading if portfolio drops too much
# Protects capital during bad days/crashes

import json
import os
import logging
import math
import shutil
from datetime import datetime, timedelta
from config.settings import MAX_DAILY_LOSS, MAX_DRAWDOWN, MAX_WEEKLY_LOSS

logger = logging.getLogger(__name__)

CIRCUIT_BREAKER_FILE = 'logs/circuit_breaker.json'

# Risk thresholds
DAILY_LOSS_LIMIT     = MAX_DAILY_LOSS
TOTAL_LOSS_LIMIT     = MAX_DRAWDOWN
WEEKLY_LOSS_LIMIT    = MAX_WEEKLY_LOSS


class RiskCircuitBreaker:
    """
    Portfolio protection system.
    Automatically stops trading during bad periods.
    Like a fuse box for your trading account!
    """

    def __init__(self):
        self.state = self._load_state()

    @staticmethod
    def _default_state():
        return {
            'triggered'       : False,
            'trigger_reason'  : None,
            'trigger_date'    : None,
            'daily_start'     : None,
            'daily_start_val' : None,
            'weekly_start'    : None,
            'weekly_start_val': None,
        }

    @classmethod
    def _valid_state(cls, state):
        """Reject malformed or non-finite persisted risk values."""
        if not isinstance(state, dict):
            return False
        if not isinstance(state.get('triggered'), bool):
            return False
        for key in ('daily_start_val', 'weekly_start_val'):
            value = state.get(key)
            if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0):
                return False
        return True

    def _load_state(self):
        """Load circuit breaker state."""
        backup_file = CIRCUIT_BREAKER_FILE + '.bak'
        if not os.path.exists(CIRCUIT_BREAKER_FILE) and not os.path.exists(backup_file):
            return self._default_state()
        errors = []
        for source, candidate in (("PRIMARY", CIRCUIT_BREAKER_FILE), ("BACKUP", backup_file)):
            try:
                with open(candidate, 'r') as f:
                    state = json.load(f)
                if not self._valid_state(state):
                    raise ValueError('circuit-breaker state failed validation')
                if source == "BACKUP":
                    restore_tmp = CIRCUIT_BREAKER_FILE + '.restore.tmp'
                    shutil.copy2(backup_file, restore_tmp)
                    os.replace(restore_tmp, CIRCUIT_BREAKER_FILE)
                    logger.warning("Recovered circuit-breaker state from validated backup")
                return {**self._default_state(), **state}
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                errors.append(f"{source}: {exc}")
        if errors:
            logger.error(
                "Circuit-breaker state is unreadable; trading blocked fail-safe: %s",
                "; ".join(errors),
            )
            state = self._default_state()
            state.update({
                'triggered': True,
                'trigger_reason': 'Invalid circuit-breaker state; manual review required',
                'trigger_date': datetime.now().isoformat(),
            })
            return state

    def _save_state(self):
        """Save circuit breaker state."""
        os.makedirs('logs', exist_ok=True)
        tmp_file = CIRCUIT_BREAKER_FILE + '.tmp'
        with open(tmp_file, 'w') as f:
            json.dump(self.state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, CIRCUIT_BREAKER_FILE)
        try:
            backup_tmp = CIRCUIT_BREAKER_FILE + '.bak.tmp'
            shutil.copy2(CIRCUIT_BREAKER_FILE, backup_tmp)
            os.replace(backup_tmp, CIRCUIT_BREAKER_FILE + '.bak')
        except OSError as exc:
            logger.warning("Circuit-breaker backup refresh failed: %s", exc)

    def check(self, current_value, starting_capital, telegram=None):
        """
        Check if circuit breaker should trigger.
        Returns True if trading should STOP.
        """
        if (isinstance(current_value, bool)
                or not isinstance(current_value, (int, float))
                or not math.isfinite(current_value)
                or current_value < 0
                or isinstance(starting_capital, bool)
                or not isinstance(starting_capital, (int, float))
                or not math.isfinite(starting_capital)
                or starting_capital <= 0):
            self._trigger("Invalid portfolio valuation; trading stopped fail-safe", telegram)
            return True

        now = datetime.now()

        # Initialize daily tracking
        today = now.strftime('%Y-%m-%d')
        if self.state.get('daily_start') != today:
            self.state['daily_start']     = today
            self.state['daily_start_val'] = current_value
            self._save_state()

        # Initialize weekly tracking
        week_start = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
        if self.state.get('weekly_start') != week_start:
            self.state['weekly_start']      = week_start
            self.state['weekly_start_val']  = current_value
            self._save_state()

        # Check if already triggered
        if self.state.get('triggered'):
            trigger_date = self.state.get('trigger_date', '')
            print(f"\n   ⚠️ CIRCUIT BREAKER ACTIVE!")
            print(f"   Triggered: {trigger_date}")
            print(f"   Reason: {self.state.get('trigger_reason')}")
            print(f"   Status: No new trades allowed")

            # Auto-reset after 24 hours
            try:
                trigger_dt = datetime.fromisoformat(trigger_date)
                if (now - trigger_dt).total_seconds() > 86400:
                    print("   Auto-resetting after 24 hours...")
                    self.reset()
                    # Continue through all loss checks. A time-based reset must
                    # never reopen trading while the loss condition persists.
                else:
                    return True
            except Exception:
                return True

        # Calculate losses
        daily_start  = self.state.get('daily_start_val', current_value)
        weekly_start = self.state.get('weekly_start_val', current_value)

        daily_loss   = (current_value - daily_start) / daily_start if daily_start > 0 else 0
        weekly_loss  = (current_value - weekly_start) / weekly_start if weekly_start > 0 else 0
        total_loss   = ((current_value - starting_capital) / starting_capital
                        if starting_capital > 0 else 0)

        print(f"\n   Risk Check:")
        print(f"   Daily P&L:   {daily_loss:+.2%}")
        print(f"   Weekly P&L:  {weekly_loss:+.2%}")
        print(f"   Total P&L:   {total_loss:+.2%}")

        # Check daily loss limit
        if daily_loss <= -DAILY_LOSS_LIMIT:
            reason = f"Daily loss limit hit: {daily_loss:.2%} (limit: -{DAILY_LOSS_LIMIT:.0%})"
            self._trigger(reason, telegram)
            return True

        # Check total loss limit
        if total_loss <= -TOTAL_LOSS_LIMIT:
            reason = f"Total loss limit hit: {total_loss:.2%} (limit: -{TOTAL_LOSS_LIMIT:.0%})"
            self._trigger(reason, telegram)
            return True

        # Weekly losses are a hard limit, consistent with the configured risk
        # threshold and the daily/total protections.
        if weekly_loss <= -WEEKLY_LOSS_LIMIT:
            reason = f"Weekly loss limit hit: {weekly_loss:.2%} (limit: -{WEEKLY_LOSS_LIMIT:.0%})"
            self._trigger(reason, telegram)
            return True

        print(f"   ✅ Risk check passed - Trading allowed")
        return False

    def _trigger(self, reason, telegram=None):
        """Trigger the circuit breaker."""
        self.state['triggered']       = True
        self.state['trigger_reason']  = reason
        self.state['trigger_date']    = datetime.now().isoformat()
        self._save_state()

        print(f"\n   🚨 CIRCUIT BREAKER TRIGGERED!")
        print(f"   Reason: {reason}")
        print(f"   All new trades STOPPED!")
        print(f"   Will auto-reset in 24 hours")

        if telegram:
            telegram.send_message(
                f"🚨 ALPHAEDGE CIRCUIT BREAKER!\n"
                f"========================\n"
                f"Reason: {reason}\n"
                f"Action: All new trades STOPPED\n"
                f"Reset: Automatic in 24 hours\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Your capital is being protected."
            )

    def reset(self, manual=False):
        """Reset the circuit breaker."""
        self.state['triggered']      = False
        self.state['trigger_reason'] = None
        self.state['trigger_date']   = None
        self._save_state()

        if manual:
            print("   Circuit breaker manually reset ✅")
        else:
            print("   Circuit breaker auto-reset after 24 hours ✅")

    def is_triggered(self):
        """Check if circuit breaker is active."""
        return self.state.get('triggered', False)

    def get_status(self):
        """Get current circuit breaker status."""
        return {
            'triggered'    : self.state.get('triggered', False),
            'reason'       : self.state.get('trigger_reason'),
            'trigger_date' : self.state.get('trigger_date'),
            'daily_limit'  : f"{DAILY_LOSS_LIMIT:.0%}",
            'total_limit'  : f"{TOTAL_LOSS_LIMIT:.0%}",
            'weekly_limit' : f"{WEEKLY_LOSS_LIMIT:.0%}",
        }


if __name__ == '__main__':
    print("\nTesting Risk Circuit Breaker...")
    cb = RiskCircuitBreaker()

    # Test normal conditions
    print("\n--- Normal Market ---")
    triggered = cb.check(
        current_value    = 10050.0,
        starting_capital = 10000.0,
    )
    print(f"Trading allowed: {not triggered}")

    # Test daily loss scenario
    print("\n--- Bad Day Scenario (-6%) ---")
    cb.state['daily_start_val'] = 10000.0
    triggered = cb.check(
        current_value    = 9400.0,
        starting_capital = 10000.0,
    )
    print(f"Trading allowed: {not triggered}")

    # Reset for next test
    cb.reset()

    # Test total loss scenario
    print("\n--- Total Loss Scenario (-12%) ---")
    triggered = cb.check(
        current_value    = 8800.0,
        starting_capital = 10000.0,
    )
    print(f"Trading allowed: {not triggered}")
