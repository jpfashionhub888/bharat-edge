# bharat_paper_trader.py
# BHARAT EDGE - Paper Trading Engine
# Tracks virtual trades in INR

import json
import os
import logging
import math
from datetime import datetime
from config.settings import (
    MAX_OPEN_POSITIONS, MAX_POSITION_SIZE, STOP_LOSS_PCT,
    TAKE_PROFIT_PCT, TRAILING_STOP_PCT,
)

logger = logging.getLogger(__name__)


class BharatPaperTrader:
    """
    Paper trading engine for Indian markets.
    Tracks positions in INR.
    Starting capital: 1,00,000 INR
    """

    def __init__(self,
                 starting_capital=100000.0,
                 max_position_pct=MAX_POSITION_SIZE,
                 max_positions=MAX_OPEN_POSITIONS,
                 log_file='logs/bharat_trades.json',
                 trade_tracker=None):

        if not self._positive_number(starting_capital):
            raise ValueError("starting_capital must be a positive finite number")
        if (not self._positive_number(max_position_pct)
                or float(max_position_pct) > 1):
            raise ValueError("max_position_pct must be in the range (0, 1]")
        if isinstance(max_positions, bool) or not isinstance(max_positions, int) or max_positions < 1:
            raise ValueError("max_positions must be a positive integer")

        self.starting_capital = float(starting_capital)
        self.capital = float(starting_capital)
        self.max_position_pct = float(max_position_pct)
        self.max_positions = max_positions
        self.log_file = log_file
        self.positions = {}
        self.trade_history = []
        self.trade_tracker = trade_tracker   # optional TradeTracker instance
        self.state_healthy = True

    @staticmethod
    def _finite_number(value):
        return (not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(value))

    @classmethod
    def _positive_number(cls, value):
        return cls._finite_number(value) and value > 0

    @classmethod
    def _valid_positions(cls, positions):
        if not isinstance(positions, dict):
            return False
        for symbol, position in positions.items():
            if not isinstance(symbol, str) or not symbol.strip() or not isinstance(position, dict):
                return False
            shares = position.get('shares')
            if isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
                return False
            for key in ('entry_price', 'highest_price', 'cost'):
                if not cls._positive_number(position.get(key)):
                    return False
        return True

    def get_position_size(self, price, signal_strength=1.0):
        if not self._positive_number(price):
            return 0
        if not self._finite_number(signal_strength):
            return 0
        # Scanner confidence is a percentage; sizing needs a 0..1 multiplier.
        if signal_strength > 1:
            signal_strength /= 100.0
        signal_strength = min(1.0, max(0.0, float(signal_strength)))
        max_inr = self.capital * self.max_position_pct
        adjusted = max_inr * signal_strength
        shares = int(adjusted / price)
        return max(shares, 0)

    def open_position(self, symbol, price, signal, reason='signal', atr=None,
                      position_multiplier=1.0):
        if not self.state_healthy:
            logger.error("New position blocked because portfolio state is unhealthy")
            return False
        if not isinstance(symbol, str) or not symbol.strip():
            return False
        if not self._positive_number(price) or not self._finite_number(signal):
            return False
        if (not self._finite_number(position_multiplier)
                or not 0 <= position_multiplier <= 1):
            return False
        if atr is not None and not self._positive_number(atr):
            atr = None
        if len(self.positions) >= self.max_positions:
            logger.info("Max positions reached, skipping")
            return False

        if symbol in self.positions:
            logger.info(f"Already in {symbol}, skipping")
            return False

        shares = self.get_position_size(price, signal * position_multiplier)
        if shares == 0:
            return False

        cost = shares * price
        if cost > self.capital:
            shares = int(self.capital * 0.95 / price)
            cost = shares * price

        if shares == 0:
            return False

        previous_capital = self.capital
        self.capital -= cost

        if atr and atr > 0:
            atr_stop_pct = (2 * atr) / price
            stop_loss_pct = max(0.02, min(0.08, atr_stop_pct))
        else:
            stop_loss_pct = STOP_LOSS_PCT

        self.positions[symbol] = {
            'shares'        : shares,
            'entry_price'   : price,
            'entry_date'    : datetime.now().isoformat(),
            'highest_price' : price,
            'signal'        : signal,
            'cost'          : cost,
            'reason'        : reason,
            'stop_loss_pct' : stop_loss_pct,
            'atr'           : atr or 0,
            'position_multiplier': position_multiplier,
        }
        trade = {
            'action': 'BUY',
            'symbol': symbol,
            'shares': shares,
            'price': price,
            'cost': cost,
            'date': datetime.now().isoformat(),
            'reason': reason,
            'signal': signal,
            'stop_loss_pct': stop_loss_pct,
            'position_multiplier': position_multiplier,
        }
        self.trade_history.append(trade)

        try:
            self.save_state()
        except Exception:
            self.capital = previous_capital
            self.positions.pop(symbol, None)
            self.trade_history.pop()
            raise

        print(f"   BUY {shares} {symbol} @ Rs{price:.2f} (Rs{cost:.2f})")
        return True

    def close_position(self, symbol, price, reason='signal'):
        if symbol not in self.positions or not self._positive_number(price):
            return False

        pos = self.positions[symbol]
        shares = pos['shares']
        entry = pos['entry_price']
        revenue = shares * price
        pnl = revenue - pos['cost']
        pnl_pct = (price - entry) / entry

        self.capital += revenue

        trade = {
            'action': 'SELL',
            'symbol': symbol,
            'shares': shares,
            'price': price,
            'revenue': revenue,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'date': datetime.now().isoformat(),
            'reason': reason,
        }
        self.trade_history.append(trade)

        direction = "PROFIT" if pnl > 0 else "LOSS"
        print(
            f"   SELL {shares} {symbol} @ Rs{price:.2f}"
            f" PnL: Rs{pnl:+.2f} ({pnl_pct:+.1%}) [{direction}]"
        )

        del self.positions[symbol]
        try:
            self.save_state()
        except Exception:
            self.capital -= revenue
            self.positions[symbol] = pos
            self.trade_history.pop()
            raise

        # The primary portfolio close is durable before secondary analytics.
        if self.trade_tracker:
            try:
                self.trade_tracker.record_trade(
                    symbol      = symbol,
                    entry_price = entry,
                    exit_price  = price,
                    shares      = shares,
                    reason      = reason.upper().replace('_', ' '),
                    entry_time  = pos.get('entry_date'),
                    exit_time   = trade['date'],
                )
            except Exception as e:
                logger.warning('TradeTracker record failed: %s', e)
        return True

    def update_position(self, symbol, current_price,
                        stop_loss=STOP_LOSS_PCT,
                        take_profit=TAKE_PROFIT_PCT,
                        trailing_stop=TRAILING_STOP_PCT):

        if symbol not in self.positions or not self._positive_number(current_price):
            return False

        pos = self.positions[symbol]
        entry = pos['entry_price']

        high_water_changed = current_price > pos['highest_price']
        if high_water_changed:
            pos['highest_price'] = current_price

        pnl_pct = (current_price - entry) / entry

        # Use position specific ATR stop loss
        stop_loss = pos.get('stop_loss_pct', stop_loss)

        # Stop loss
        if pnl_pct <= -stop_loss:
            print(
                f"   STOP LOSS: {symbol} "
                f"down {pnl_pct:.1%} "
                f"(limit: -{stop_loss:.1%})"
            )
            self.close_position(
                symbol, current_price, 'stop_loss'
            )
            return True

        if pnl_pct >= take_profit:
            self.close_position(symbol, current_price, 'take_profit')
            return True

        drop = (pos['highest_price'] - current_price) / pos['highest_price']
        if drop >= trailing_stop:
            self.close_position(symbol, current_price, 'trailing_stop')
            return True

        if high_water_changed:
            self.save_state()

        return False

    def get_portfolio_value(self, current_prices):
        position_value = 0.0
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos['entry_price'])
            if not self._positive_number(price):
                price = pos['entry_price']
            position_value += pos['shares'] * price
        return self.capital + position_value

    def get_summary(self, current_prices=None):
        if current_prices is None:
            current_prices = {}

        position_value = 0.0
        print("\n" + "="*60)
        print("BHARAT EDGE PAPER TRADING PORTFOLIO")
        print("="*60)
        print(f"   Cash: Rs{self.capital:,.2f}")

        if self.positions:
            print("\n   Open Positions:")
            for symbol, pos in self.positions.items():
                shares = pos['shares']
                entry = pos['entry_price']
                curr = current_prices.get(symbol, entry)
                val = shares * curr
                pnl = val - pos['cost']
                pnl_pct = (curr - entry) / entry
                position_value += val
                direction = "UP" if pnl > 0 else "DOWN"
                print(
                    f"      {direction} {symbol}: {shares} shares"
                    f" @ Rs{entry:.2f}"
                    f" now Rs{curr:.2f}"
                    f" PnL: Rs{pnl:+.2f} ({pnl_pct:+.1%})"
                )

        total = self.capital + position_value
        total_pnl = total - self.starting_capital
        total_pct = total_pnl / self.starting_capital

        print(f"\n   Position Value: Rs{position_value:,.2f}")
        print(f"   Total Value: Rs{total:,.2f}")
        print(f"   Total PnL: Rs{total_pnl:+,.2f} ({total_pct:+.1%})")
        print(f"   Total Trades: {len(self.trade_history)}")
        print("="*60)
        return total

    def save_state(self):
        state = {
            'capital': self.capital,
            'starting_capital': self.starting_capital,
            'positions': self.positions,
            'trade_history': self.trade_history,
            'saved_at': datetime.now().isoformat(),
        }
        os.makedirs(os.path.dirname(self.log_file) or '.', exist_ok=True)
        # Atomic write: temp file then rename to prevent truncation on crash
        tmp_file = self.log_file + '.tmp'
        with open(tmp_file, 'w') as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, self.log_file)
        print(f"   State saved to {self.log_file}")

    def load_state(self):
        if not os.path.exists(self.log_file):
            print("   No saved state found, starting fresh")
            self.state_healthy = True
            return

        try:
            with open(self.log_file, 'r') as f:
                state = json.load(f)
            capital = float(state['capital'])
            starting_capital = float(state['starting_capital'])
            positions = state.get('positions', {})
            trade_history = state.get('trade_history', [])
            if (not self._finite_number(capital) or capital < 0
                    or not self._positive_number(starting_capital)
                    or not self._valid_positions(positions)
                    or not isinstance(trade_history, list)):
                raise ValueError("paper-trading state failed validation")
            self.capital = capital
            self.starting_capital = starting_capital
            self.positions = positions
            self.trade_history = trade_history
            self.state_healthy = True
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            logger.error("Ignoring invalid paper-trading state %s: %s", self.log_file, exc)
            # Never interpret a damaged account file as a fresh empty account.
            # Existing in-memory positions remain manageable, but new entries
            # stay blocked until an operator repairs or removes the state file.
            self.state_healthy = False
            return

        print(f"   State loaded: Rs{self.capital:,.2f} cash")
        print(f"   Open positions: {len(self.positions)}")
