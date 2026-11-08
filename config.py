import os
from dotenv import load_dotenv

load_dotenv()

# --- API Credentials ---
API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
USE_TESTNET = os.getenv("USE_TESTNET", "True").lower() == "true"

# --- Exchange ---
EXCHANGE_ID = "binanceusdm"  # Binance USDT-M Futures via ccxt
TESTNET_URLS = {
    "api": "https://testnet.binancefuture.com",
    "fapiPublic": "https://testnet.binancefuture.com/fapi/v1",
    "fapiPrivate": "https://testnet.binancefuture.com/fapi/v1",
    "fapiPublicV2": "https://testnet.binancefuture.com/fapi/v2",
    "fapiPrivateV2": "https://testnet.binancefuture.com/fapi/v2",
}

# --- Trading Parameters ---
SYMBOL = os.getenv("SYMBOL", "BTC/USDT:USDT")
TIMEFRAME = os.getenv("TIMEFRAME", "15m")
LEVERAGE = int(os.getenv("LEVERAGE", 5))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", 1.0))   # % of balance
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 2))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", 5.0))  # %

# --- Indicator Parameters ---
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
ATR_PERIOD = 14
VOLUME_MA_PERIOD = 20

# --- Risk/Reward ---
ATR_SL_MULTIPLIER = 1.0   # Stop loss = 1x ATR
ATR_TP_MULTIPLIER = 2.0   # Take profit = 2x ATR

# --- Telegram Alerts ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Candle fetch count ---
CANDLE_LIMIT = 200   # Number of candles to fetch for indicator calculation

