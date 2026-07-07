# monitoring/trade_tracker.py
"""
BharatEdge Trade Tracker

Logs every closed paper trade to a structured JSON file and
fires Telegram milestone alerts at 25 and 50 closed trades.

Used by:
  - bharat_cloud_scan.py  (writes a closed trade on every stop/take-profit)
  - monitoring/command_listener.py  (reads stats for /status)
  - monitoring/model_watchdog.py    (reads stats for 6h watchdog report)

File: logs/closed_trades.json
Schema:
  {
    "trades": [
      {
        "id": 1,
        "symbol": "RELIANCE",
        "entry_price": 2850.00,
        "exit_price": 2963.00,
        "shares": 3,
        "pnl_inr": 339.00,
        "pnl_pct": 3.96,
        "reason": "TAKE PROFIT",
        "entry_time": "2026-07-07T09:15:00",
        "exit_time":  "2026-07-09T14:22:00",
        "hold_days": 2
      },
      ...
    ],
    "summary": {
      "total": 3,
      "wins": 2,
      "losses": 1,
      "win_rate": 0.667,
      "total_pnl": 1120.50,
      "avg_win": 750.25,
      "avg_loss": -380.00,
      "profit_factor": 3.97,
      "last_updated": "2026-07-09T14:22:00"
    }
  }
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TRADES_FILE     = 'logs/closed_trades.json'
MILESTONE_25    = 25
MILESTONE_50    = 50


# ── Trade Tracker ─────────────────────────────────────────────

class TradeTracker:
    """
    Records closed trades and computes running statistics.
    Thread-safe (uses a lock for all writes).
    """

    def __init__(self, trades_file: str = TRADES_FILE, telegram=None):
        """
        Parameters
        ----------
        trades_file : path to JSON file for persistence
        telegram    : BharatTelegram instance for milestone alerts (optional)
        """
        self.trades_file = trades_file
        self.telegram    = telegram
        self._lock       = threading.Lock()
        self._data       = self._load()

    # ── Public API ────────────────────────────────────────────

    def record_trade(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        shares: float,
        reason: str,
        entry_time: str | None = None,
        exit_time:  str | None = None,
    ) -> dict:
        """
        Record a single closed trade and update running summary.

        Parameters
        ----------
        symbol      : NSE ticker (e.g. 'RELIANCE')
        entry_price : average entry price in ₹
        exit_price  : exit price in ₹
        shares      : number of shares
        reason      : 'TAKE PROFIT', 'STOP LOSS', 'TRAILING STOP', 'SIGNAL', etc.
        entry_time  : ISO timestamp string (defaults to now)
        exit_time   : ISO timestamp string (defaults to now)

        Returns
        -------
        dict with the recorded trade and updated summary
        """
        now_str   = datetime.now().isoformat()
        entry_ts  = entry_time or now_str
        exit_ts   = exit_time  or now_str

        pnl_inr   = (exit_price - entry_price) * shares
        pnl_pct   = ((exit_price - entry_price) / entry_price) * 100 if entry_price else 0.0

        # Compute hold days
        try:
            e = datetime.fromisoformat(entry_ts)
            x = datetime.fromisoformat(exit_ts)
            hold_days = max(0, (x.date() - e.date()).days)
        except Exception:
            hold_days = 0

        with self._lock:
            trade_id = len(self._data['trades']) + 1
            trade = {
                'id'          : trade_id,
                'symbol'      : symbol,
                'entry_price' : round(entry_price, 2),
                'exit_price'  : round(exit_price, 2),
                'shares'      : shares,
                'pnl_inr'     : round(pnl_inr, 2),
                'pnl_pct'     : round(pnl_pct, 2),
                'reason'      : reason,
                'entry_time'  : entry_ts,
                'exit_time'   : exit_ts,
                'hold_days'   : hold_days,
            }
            self._data['trades'].append(trade)
            self._data['summary'] = self._compute_summary()
            self._save()
            total = self._data['summary']['total']

        logger.info(
            'Trade #%d recorded: %s %s @ ₹%.2f → ₹%.2f  P&L: ₹%+.2f (%.1f%%)',
            trade_id, reason, symbol, entry_price, exit_price, pnl_inr, pnl_pct
        )

        # Milestone alerts
        self._check_milestones(total)

        return {'trade': trade, 'summary': self._data['summary']}

    def get_stats(self) -> dict:
        """Return current summary statistics."""
        with self._lock:
            return dict(self._data['summary'])

    def get_trades(self) -> list:
        """Return list of all recorded trades."""
        with self._lock:
            return list(self._data['trades'])

    # ── Internal helpers ──────────────────────────────────────

    def _compute_summary(self) -> dict:
        """Recompute all statistics from trade list. Call inside lock."""
        trades  = self._data['trades']
        total   = len(trades)
        wins    = [t for t in trades if t['pnl_inr'] > 0]
        losses  = [t for t in trades if t['pnl_inr'] <= 0]

        win_count  = len(wins)
        loss_count = len(losses)
        win_rate   = win_count / total if total else 0.0

        total_pnl  = sum(t['pnl_inr'] for t in trades)
        avg_win    = sum(t['pnl_inr'] for t in wins)  / win_count  if wins   else 0.0
        avg_loss   = sum(t['pnl_inr'] for t in losses) / loss_count if losses else 0.0

        gross_profit = sum(t['pnl_inr'] for t in wins)
        gross_loss   = abs(sum(t['pnl_inr'] for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
            float('inf') if gross_profit > 0 else 0.0
        )

        return {
            'total'         : total,
            'wins'          : win_count,
            'losses'        : loss_count,
            'win_rate'      : round(win_rate, 4),
            'total_pnl'     : round(total_pnl, 2),
            'avg_win'       : round(avg_win, 2),
            'avg_loss'      : round(avg_loss, 2),
            'profit_factor' : round(profit_factor, 4) if profit_factor != float('inf') else None,
            'last_updated'  : datetime.now().isoformat(),
        }

    def _check_milestones(self, total: int) -> None:
        """Fire Telegram alert at 25 and 50 trades."""
        if total not in (MILESTONE_25, MILESTONE_50):
            return
        if not self.telegram:
            return

        stats = self.get_stats()
        wr    = stats['win_rate'] * 100
        pf    = stats['profit_factor'] or 0
        pnl   = stats['total_pnl']

        if total == MILESTONE_25:
            title = '🎯 25 Trades Milestone!'
            note  = 'Halfway to live eligibility review.'
        else:
            title = '🚀 50 Trades Milestone!'
            note  = 'Live eligibility criteria reached! Review go/no-go.'

        msg = (
            f'{title}\n'
            f'{"=" * 30}\n'
            f'Total trades : {total}\n'
            f'Win rate     : {wr:.1f}%  (need ≥55%)\n'
            f'Profit factor: {pf:.2f}  (need ≥1.5)\n'
            f'Total P&L    : ₹{pnl:+,.2f}\n\n'
            f'{note}'
        )
        try:
            self.telegram.send_message(msg)
        except Exception as e:
            logger.warning('Milestone alert send failed: %s', e)

    def _load(self) -> dict:
        """Load trade data from file, or create fresh structure."""
        try:
            with open(self.trades_file) as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                'trades'  : [],
                'summary' : {
                    'total'         : 0,
                    'wins'          : 0,
                    'losses'        : 0,
                    'win_rate'      : 0.0,
                    'total_pnl'     : 0.0,
                    'avg_win'       : 0.0,
                    'avg_loss'      : 0.0,
                    'profit_factor' : 0.0,
                    'last_updated'  : None,
                },
            }
        except Exception as e:
            logger.warning('Could not load trade tracker file: %s', e)
            return {'trades': [], 'summary': {}}

    def _save(self) -> None:
        """Persist trade data to JSON file. Call inside lock."""
        try:
            os.makedirs(os.path.dirname(self.trades_file) or '.', exist_ok=True)
            with open(self.trades_file, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.warning('Could not save trade tracker file: %s', e)


# ── Convenience function (used by command_listener + watchdog) ─

def get_trade_stats(trades_file: str = TRADES_FILE) -> dict:
    """
    Quick read of trade summary — no lock needed (read-only).
    Returns empty dict if file doesn't exist.
    """
    try:
        with open(trades_file) as f:
            data = json.load(f)
        return data.get('summary', {})
    except Exception:
        return {}
