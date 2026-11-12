import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

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
# Supports comma-separated symbols, e.g. BTCUSDT,ETHUSDT,XRPUSDT,SOLUSDT
SYMBOLS_RAW = os.getenv("SYMBOLS", os.getenv("SYMBOL", "BTCUSDT,ETHUSDT,XRPUSDT"))
SYMBOLS = [s.strip().replace("/", "").replace(":USDT", "") for s in SYMBOLS_RAW.split(",") if s.strip()]
SYMBOL = SYMBOLS[0] if SYMBOLS else "BTCUSDT"  # Backward compatibility
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

# --- Risk/Reward & Volatility Filters ---
ATR_SL_MULTIPLIER = 1.0   # Stop loss = 1x ATR
ATR_TP_MULTIPLIER = 2.0   # Take profit = 2x ATR
MIN_ATR_PCT = float(os.getenv("MIN_ATR_PCT", 0.5))  # Min ATR % of price to avoid low-vol fee drag

# --- Telegram Alerts ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Candle fetch count ---
CANDLE_LIMIT = 200   # Number of candles to fetch for indicator calculation

