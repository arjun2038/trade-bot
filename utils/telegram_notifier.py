"""
utils/telegram_notifier.py
Sends trade alerts and status updates to Telegram.
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
"""

import requests
from utils.logger import get_logger

logger = get_logger("telegram")


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}/sendMessage" if token else ""
        self.enabled = bool(token and chat_id and token != "your_bot_token_here" and chat_id != "your_chat_id_here")

        if not self.enabled:
            logger.warning("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env to receive alerts.")

    def send(self, message: str):
        """Send a plain text or Markdown message."""
        if not self.enabled:
            return
        try:
            resp = requests.post(
                self.base_url,
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    def alert_trade_opened(self, signal: dict, qty: float, symbol: str):
        direction = signal["signal"].upper()
        emoji = "🟢" if signal["signal"] == "long" else "🔴"
        msg = (
            f"{emoji} *TRADE OPENED — {direction}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Symbol:       `{symbol}`\n"
            f"💰 Entry:        `{signal['entry']}`\n"
            f"🔒 Stop Loss:   `{signal['stop_loss']}`\n"
            f"🎯 Take Profit: `{signal['take_profit']}`\n"
            f"📦 Quantity:    `{qty}`\n"
            f"📊 RSI:         `{signal.get('rsi', 'N/A')}`\n"
            f"📐 ATR:         `{signal.get('atr', 'N/A')}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"_{signal.get('reason', '')}_"
        )
        self.send(msg)

    def alert_no_signal(self, reason: str):
        self.send(f"⏳ *No Signal* — {reason}")

    def alert_daily_loss_limit(self, balance: float, loss_pct: float):
        msg = (
            f"🚨 *DAILY LOSS LIMIT HIT*\n"
            f"Loss: `{loss_pct:.2f}%`\n"
            f"Balance: `{balance:.2f} USDT`\n"
            f"Bot paused for the day."
        )
        self.send(msg)

    def alert_order_reconciled(self, symbol: str, order_type: str, order_id: str | int):
        msg = (
            f"🧹 *OCO RECONCILIATION*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Symbol:    `{symbol}`\n"
            f"🗑️ Cancelled: `{order_type}` (#{order_id})\n"
            f"ℹ️ _Position closed; cancelled lingering exit order._"
        )
        self.send(msg)

    def alert_error(self, error: str):
        self.send(f"❌ *Bot Error*\n`{error}`")

    def alert_startup(self, symbol: str, timeframe: str, testnet: bool):
        env = "🧪 TESTNET" if testnet else "🔴 LIVE"
        msg = (
            f"🚀 *Bot Started* {env}\n"
            f"Symbol: `{symbol}`\n"
            f"Timeframe: `{timeframe}`"
        )
        self.send(msg)

    def alert_daily_summary(self, balance: float, pnl: float, trades: int):
        emoji = "✅" if pnl >= 0 else "❌"
        msg = (
            f"{emoji} *Daily Summary*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💼 Balance:  `{balance:.2f} USDT`\n"
            f"📈 PnL:      `{pnl:+.2f} USDT`\n"
            f"🔢 Trades:   `{trades}`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        self.send(msg)

