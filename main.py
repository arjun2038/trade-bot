"""
main.py
Entry point for the Binance Futures Intraday Trading Bot.
Runs the strategy loop on a 15-minute schedule.

Usage:
    python main.py           # Live trading loop
    python main.py --backtest  # Run backtest only
"""

import sys
import time
import schedule
from datetime import datetime

import config as cfg
from data.fetcher import fetch_ohlcv
from strategy.ema_rsi_atr import generate_signal
from execution.order_manager import OrderManager
from risk.risk_manager import RiskManager
from utils.telegram_notifier import TelegramNotifier
from utils.logger import get_logger

logger = get_logger("main")

# ─────────────────────────────────────────────
#  Config dict (passed to strategy/risk modules)
# ─────────────────────────────────────────────
CONFIG = {
    "EMA_FAST": cfg.EMA_FAST,
    "EMA_SLOW": cfg.EMA_SLOW,
    "RSI_PERIOD": cfg.RSI_PERIOD,
    "ATR_PERIOD": cfg.ATR_PERIOD,
    "VOLUME_MA_PERIOD": cfg.VOLUME_MA_PERIOD,
    "ATR_SL_MULTIPLIER": cfg.ATR_SL_MULTIPLIER,
    "ATR_TP_MULTIPLIER": cfg.ATR_TP_MULTIPLIER,
    "RISK_PER_TRADE": cfg.RISK_PER_TRADE,
    "DAILY_LOSS_LIMIT": cfg.DAILY_LOSS_LIMIT,
    "MAX_OPEN_TRADES": cfg.MAX_OPEN_TRADES,
}

# Binance symbol format (no slash, no colon)
BINANCE_SYMBOL = cfg.SYMBOL.replace("/", "").replace(":USDT", "")  # e.g. BTCUSDT

# Module instances (initialized in main)
order_mgr = None
risk_mgr = None
telegram = None


def run_strategy():
    """Main strategy execution — called every candle close."""
    logger.info(f"{'='*50}")
    logger.info(f"Running strategy @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Fetch candles
    df = fetch_ohlcv(
        symbol=BINANCE_SYMBOL,
        interval=cfg.TIMEFRAME,
        limit=cfg.CANDLE_LIMIT,
        use_testnet=cfg.USE_TESTNET
    )
    if df.empty:
        logger.warning("No candle data received. Skipping this cycle.")
        return

    # 2. Get balance
    balance = order_mgr.get_balance()
    if balance <= 0:
        logger.warning("Balance is 0 or failed to fetch. Ensure valid API keys are configured in .env. Skipping trade cycle.")
        return

    # 3. Daily loss check
    risk_mgr.set_balance(balance)
    if risk_mgr.is_daily_loss_hit(balance):
        logger.warning("Daily loss limit reached. No new trades today.")
        telegram.alert_daily_loss_limit(balance, cfg.DAILY_LOSS_LIMIT)
        return

    # 4. Check open positions
    open_positions = order_mgr.get_open_positions(BINANCE_SYMBOL)
    logger.info(f"Open positions: {len(open_positions)}")

    if not risk_mgr.can_open_trade(len(open_positions)):
        return

    # 5. Generate signal
    signal = generate_signal(df, CONFIG)
    logger.info(f"Signal: {signal['signal'].upper()} | {signal['reason']}")

    if signal["signal"] == "none":
        logger.info("No trade signal this cycle.")
        return

    # 6. Calculate position size
    qty = risk_mgr.calculate_position_size(
        balance=balance,
        entry=signal["entry"],
        stop_loss=signal["stop_loss"],
        leverage=cfg.LEVERAGE
    )
    qty = order_mgr.round_quantity(BINANCE_SYMBOL, qty)
    if qty <= 0:
        logger.warning("Position size is 0 after precision rounding. Skipping trade.")
        return

    # 7. Set leverage
    order_mgr.set_leverage(BINANCE_SYMBOL, cfg.LEVERAGE)

    # 8. Place entry order
    side = "BUY" if signal["signal"] == "long" else "SELL"
    exit_side = "SELL" if signal["signal"] == "long" else "BUY"

    logger.info(f"Placing {side} order: qty={qty} | entry≈{signal['entry']} "
                f"| SL={signal['stop_loss']} | TP={signal['take_profit']}")

    entry_result = order_mgr.place_market_order(BINANCE_SYMBOL, side, qty)
    if not entry_result.get("orderId"):
        logger.error("Entry order failed. Aborting.")
        return

    # 9. Place SL and TP
    order_mgr.place_stop_loss(BINANCE_SYMBOL, exit_side, qty, signal["stop_loss"])
    order_mgr.place_take_profit(BINANCE_SYMBOL, exit_side, qty, signal["take_profit"])

    logger.info(f"Trade opened successfully | ATR={signal['atr']} | RSI={signal['rsi']}")
    telegram.alert_trade_opened(signal, qty, BINANCE_SYMBOL)


def run_backtest():
    """Run backtest on 500 candles of historical data."""
    from backtest.backtester import Backtester

    logger.info("Starting backtest...")
    df = fetch_ohlcv(
        symbol=BINANCE_SYMBOL,
        interval=cfg.TIMEFRAME,
        limit=500,
        use_testnet=False  # Public endpoint — no auth needed for historical data
    )
    if df.empty:
        logger.error("Could not fetch historical data for backtest.")
        return

    bt = Backtester(CONFIG, initial_balance=10000.0)
    results = bt.run(df)

    print("\n" + "="*50)
    print("  BACKTEST RESULTS")
    print("="*50)
    for k, v in results.items():
        print(f"  {k:<25} {v}")
    print("="*50)


# ─────────────────────────────────────────────
#  Init
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("🚀 Binance Futures Intraday Bot starting...")
    logger.info(f"Symbol: {BINANCE_SYMBOL} | Timeframe: {cfg.TIMEFRAME} | Testnet: {cfg.USE_TESTNET}")

    if "--backtest" in sys.argv:
        run_backtest()
        sys.exit(0)

    # Initialize modules
    order_mgr = OrderManager(cfg.API_KEY, cfg.API_SECRET, cfg.USE_TESTNET)
    risk_mgr = RiskManager(CONFIG)
    telegram = TelegramNotifier(cfg.TELEGRAM_BOT_TOKEN, cfg.TELEGRAM_CHAT_ID)

    # Run immediately on startup
    telegram.alert_startup(BINANCE_SYMBOL, cfg.TIMEFRAME, cfg.USE_TESTNET)
    run_strategy()

    # Then schedule every 15 minutes (aligned to candle close)
    schedule.every(15).minutes.do(run_strategy)

    logger.info("Bot running. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")

