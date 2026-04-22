# bharat_telegram.py
# BHARAT EDGE - Telegram Bot (Fixed & Clean)

import requests
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')


class BharatTelegram:

    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)

        if not self.enabled:
            print("   Telegram not configured.")

    def send_message(self, text):
        if not self.enabled:
            print(f"   [Telegram disabled] {text[:50]}")
            return False

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
            }
            response = requests.post(url, json=payload, timeout=10)
            print(f"   Telegram status: {response.status_code}")
            if response.status_code == 200:
                print("   Telegram sent successfully!")
                return True
            else:
                print(f"   Telegram error: {response.text}")
                return False
        except Exception as e:
            print(f"   Telegram exception: {e}")
            return False

    def alert_buy_signal(self, symbol, price, signal, sector):
        text = (
            f"BHARAT EDGE - BUY SIGNAL\n"
            f"========================\n"
            f"Symbol: {symbol}\n"
            f"Price: Rs{price:.2f}\n"
            f"Signal Strength: {signal:.3f}\n"
            f"Sector: {sector}\n"
            f"Time: {datetime.now().strftime('%d %b %Y %H:%M IST')}"
        )
        print(f"   Sending BUY alert for {symbol}...")
        return self.send_message(text)

    def alert_stop_loss(self, symbol, price, pnl):
        text = (
            f"BHARAT EDGE - STOP LOSS\n"
            f"========================\n"
            f"Symbol: {symbol}\n"
            f"Exit Price: Rs{price:.2f}\n"
            f"Loss: Rs{pnl:.2f}\n"
            f"Position closed automatically.\n"
            f"Time: {datetime.now().strftime('%d %b %Y %H:%M IST')}"
        )
        return self.send_message(text)

    def alert_take_profit(self, symbol, price, pnl):
        text = (
            f"BHARAT EDGE - TAKE PROFIT\n"
            f"==========================\n"
            f"Symbol: {symbol}\n"
            f"Exit Price: Rs{price:.2f}\n"
            f"Profit: Rs+{pnl:.2f}\n"
            f"Time: {datetime.now().strftime('%d %b %Y %H:%M IST')}"
        )
        return self.send_message(text)

    def alert_daily_summary(self, portfolio_value,
                            total_pnl, total_pct,
                            positions, signals):

        pnl_sign = "+" if total_pnl >= 0 else ""
        pnl_direction = "UP" if total_pnl >= 0 else "DOWN"

        pos_text = ""
        if positions:
            for sym, pos in positions.items():
                shares = pos.get('shares', 0)
                entry = pos.get('entry_price', 0)
                current = pos.get('current_price', entry)
                pnl = pos.get('pnl', 0.0)
                pnl_pct = pos.get('pnl_pct', 0.0)
                p_sign = "+" if pnl >= 0 else ""
                direction = "UP" if pnl >= 0 else "DOWN"
                pos_text += (
                    f"  {sym}: {shares} shares\n"
                    f"  Entry: Rs{entry:.2f} | Now: Rs{current:.2f}\n"
                    f"  PnL: {direction} {p_sign}Rs{pnl:.2f}"
                    f" ({p_sign}{pnl_pct:.1%})\n\n"
                )
        else:
            pos_text = "  No open positions\n"

        buy_signals = [s for s, d in signals.items()
                       if d.get('signal') == 'BUY']
        avoid_signals = [s for s, d in signals.items()
                         if d.get('signal') == 'AVOID']

        text = (
            f"BHARAT EDGE DAILY SUMMARY\n"
            f"==========================\n"
            f"Time: {datetime.now().strftime('%d %b %Y %H:%M IST')}\n"
            f"\n"
            f"Portfolio: Rs{portfolio_value:,.2f}\n"
            f"Total PnL: {pnl_direction} "
            f"{pnl_sign}Rs{total_pnl:,.2f} "
            f"({pnl_sign}{total_pct:.1%})\n"
            f"\n"
            f"Open Positions:\n"
            f"{pos_text}"
            f"BUY signals: {', '.join(buy_signals) or 'None'}\n"
            f"AVOID signals: {', '.join(avoid_signals) or 'None'}\n"
            f"\n"
            f"BharatEdge AI - Automated"
        )

        print("   Sending daily summary to Telegram...")
        result = self.send_message(text)
        print(f"   Telegram result: {result}")
        return result

    def test(self):
        text = (
            f"BharatEdge Bot Connected!\n"
            f"==========================\n"
            f"Indian Market AI System\n"
            f"You will receive:\n"
            f"  BUY signals (NSE stocks)\n"
            f"  SELL alerts\n"
            f"  Daily P&L summary\n"
            f"\n"
            f"Time: {datetime.now().strftime('%d %b %Y %H:%M IST')}"
        )
        return self.send_message(text)


if __name__ == "__main__":
    bot = BharatTelegram()
    bot.test()