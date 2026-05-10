# bharat_paper_trader.py
# BHARAT EDGE - Paper Trading Engine
# Tracks virtual trades in INR

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class BharatPaperTrader:
    """
    Paper trading engine for Indian markets.
    Tracks positions in INR.
    Starting capital: 1,00,000 INR
    """

    def __init__(self,
                 starting_capital=100000.0,
                 max_position_pct=0.15,
                 max_positions=5,
                 log_file='logs/bharat_trades.json'):

        self.starting_capital = starting_capital
        self.capital = starting_capital
        self.max_position_pct = max_position_pct
        self.max_positions = max_positions
        self.log_file = log_file
        self.positions = {}
        self.trade_history = []

    def get_position_size(self, price, signal_strength=1.0):
        max_inr = self.capital * self.max_position_pct
        adjusted = max_inr * signal_strength
        shares = int(adjusted / price)
        return max(shares, 0)

    def open_position(self, symbol, price, signal, reason='signal', atr=None):
        if len(self.positions) >= self.max_positions:
            logger.info("Max positions reached, skipping")
            return False

        if symbol in self.positions:
            logger.info(f"Already in {symbol}, skipping")
            return False

        shares = self.get_position_size(price, signal)
        if shares == 0:
            return False

        cost = shares * price
        if cost > self.capital:
            shares = int(self.capital * 0.95 / price)
            cost = shares * price

        if shares == 0:
            return False

        self.capital -= cost

        if atr and atr > 0:
            atr_stop_pct = (2 * atr) / price
            stop_loss_pct = max(0.02, min(0.08, atr_stop_pct))
        else:
            stop_loss_pct = 0.04

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
        }
        trade = {
            'action': 'BUY',
            'symbol': symbol,
            'shares': shares,
            'price': price,
            'cost': cost,
            'date': datetime.now().isoformat(),
            'reason': reason,
        }
        self.trade_history.append(trade)

        print(f"   BUY {shares} {symbol} @ Rs{price:.2f} (Rs{cost:.2f})")
        return True

    def close_position(self, symbol, price, reason='signal'):
        if symbol not in self.positions:
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
        return True

    def update_position(self, symbol, current_price,
                        stop_loss=0.04,
                        take_profit=0.08,
                        trailing_stop=0.04):

        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        entry = pos['entry_price']

        if current_price > pos['highest_price']:
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
            return

        if pnl_pct >= take_profit:
            self.close_position(symbol, current_price, 'take_profit')
            return

        drop = (pos['highest_price'] - current_price) / pos['highest_price']
        if drop >= trailing_stop:
            self.close_position(symbol, current_price, 'trailing_stop')
            return

    def get_portfolio_value(self, current_prices):
        position_value = 0.0
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos['entry_price'])
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
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, 'w') as f:
            json.dump(state, f, indent=2)
        print(f"   State saved to {self.log_file}")

    def load_state(self):
        if not os.path.exists(self.log_file):
            print("   No saved state found, starting fresh")
            return

        with open(self.log_file, 'r') as f:
            state = json.load(f)

        self.capital = state['capital']
        self.starting_capital = state['starting_capital']
        self.positions = state['positions']
        self.trade_history = state['trade_history']

        print(f"   State loaded: Rs{self.capital:,.2f} cash")
        print(f"   Open positions: {len(self.positions)}")