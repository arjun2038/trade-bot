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
    "MIN_ATR_PCT": cfg.MIN_ATR_PCT,
    "RISK_PER_TRADE": cfg.RISK_PER_TRADE,
    "DAILY_LOSS_LIMIT": cfg.DAILY_LOSS_LIMIT,
    "MAX_OPEN_TRADES": cfg.MAX_OPEN_TRADES,
}

# Binance symbols to trade
SYMBOLS = cfg.SYMBOLS

# Module instances (initialized in main)
order_mgr = None
risk_mgr = None
telegram = None


def run_strategy_for_symbol(symbol: str, balance: float, all_open_positions: list):
    """Execute strategy check for a specific symbol."""
    logger.info(f"--- Checking {symbol} ---")

    # Check if this specific symbol already has an open position
    symbol_positions = [p for p in all_open_positions if p.get("symbol") == symbol]
    if symbol_positions:
        logger.info(f"{symbol} already has an active position open. Skipping.")
        return

    # Fetch candles
    df = fetch_ohlcv(
        symbol=symbol,
        interval=cfg.TIMEFRAME,
        limit=cfg.CANDLE_LIMIT,
        use_testnet=cfg.USE_TESTNET
    )
    if df.empty:
        logger.warning(f"No candle data received for {symbol}. Skipping.")
        return

    # Generate signal
    signal = generate_signal(df, CONFIG)
    logger.info(f"{symbol} Signal: {signal['signal'].upper()} | {signal['reason']}")

    if signal["signal"] == "none":
        return

    # Calculate position size
    qty = risk_mgr.calculate_position_size(
        balance=balance,
        entry=signal["entry"],
        stop_loss=signal["stop_loss"],
        leverage=cfg.LEVERAGE
    )
    qty = order_mgr.round_quantity(symbol, qty)
    if qty <= 0:
        logger.warning(f"{symbol} Position size is 0 after precision rounding. Skipping trade.")
        return

    # Set leverage
    order_mgr.set_leverage(symbol, cfg.LEVERAGE)

    # Place entry order
    side = "BUY" if signal["signal"] == "long" else "SELL"
    exit_side = "SELL" if signal["signal"] == "long" else "BUY"

    logger.info(f"Placing {side} order for {symbol}: qty={qty} | entry≈{signal['entry']} "
                f"| SL={signal['stop_loss']} | TP={signal['take_profit']}")

    entry_result = order_mgr.place_market_order(symbol, side, qty)
    if not entry_result.get("orderId"):
        logger.error(f"Entry order failed for {symbol}. Aborting.")
        return

    # Place SL and TP
    order_mgr.place_stop_loss(symbol, exit_side, qty, signal["stop_loss"])
    order_mgr.place_take_profit(symbol, exit_side, qty, signal["take_profit"])

    logger.info(f"Trade opened successfully for {symbol} | ATR={signal['atr']} | RSI={signal['rsi']}")
    telegram.alert_trade_opened(signal, qty, symbol)


def run_strategy():
    """Main strategy execution — called every candle close across all symbols."""
    logger.info(f"{'='*50}")
    logger.info(f"Running multi-pair strategy @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Pairs monitored: {', '.join(SYMBOLS)}")

    # 0. OCO Reconciliation: Cancel any lingering orphan SL/TP orders from closed positions
    cancelled = order_mgr.reconcile_orphan_orders()
    if cancelled and telegram:
        for c in cancelled:
            telegram.alert_order_reconciled(c["symbol"], c["type"], c["orderId"])

    # 1. Get balance
    balance = order_mgr.get_balance()
    if balance <= 0:
        logger.warning("Balance is 0 or failed to fetch. Ensure valid API keys are configured in .env. Skipping trade cycle.")
        return

    # 2. Daily loss check
    risk_mgr.set_balance(balance)
    if risk_mgr.is_daily_loss_hit(balance):
        logger.warning("Daily loss limit reached. No new trades today.")
        telegram.alert_daily_loss_limit(balance, cfg.DAILY_LOSS_LIMIT)
        return

    # 3. Check open positions across all coins
    all_open_positions = order_mgr.get_open_positions("")
    logger.info(f"Total open positions across all pairs: {len(all_open_positions)}")

    # 4. Iterate over configured symbols
    for symbol in SYMBOLS:
        if not risk_mgr.can_open_trade(len(all_open_positions)):
            logger.info("Maximum open trade capacity reached for the portfolio.")
            break
        run_strategy_for_symbol(symbol, balance, all_open_positions)
        # Refresh open positions in case a trade was just opened
        all_open_positions = order_mgr.get_open_positions("")


def run_backtest():
    """Run backtest on 500 candles of historical data."""
    from backtest.backtester import Backtester

    target_symbol = SYMBOLS[0] if SYMBOLS else "BTCUSDT"
    logger.info(f"Starting backtest for {target_symbol}...")
    df = fetch_ohlcv(
        symbol=target_symbol,
        interval=cfg.TIMEFRAME,
        limit=500,
        use_testnet=False  # Public endpoint — no auth needed for historical data
    )
    if df.empty:
        logger.error(f"Could not fetch historical data for {target_symbol}.")
        return

    bt = Backtester(CONFIG, initial_balance=10000.0)
    results = bt.run(df)

    print("\n" + "="*50)
    print(f"  BACKTEST RESULTS ({target_symbol})")
    print("="*50)
    for k, v in results.items():
        print(f"  {k:<25} {v}")
    print("="*50)


# ─────────────────────────────────────────────
#  Candle Synchronization Helpers
# ─────────────────────────────────────────────

def get_interval_seconds(interval_str: str) -> int:
    """Parse timeframe string (e.g. '15m', '1h') into total seconds."""
    if interval_str.endswith("m"):
        return int(interval_str.replace("m", "")) * 60
    elif interval_str.endswith("h"):
        return int(interval_str.replace("h", "")) * 3600
    return 900


def sleep_until_next_candle(
    order_manager=None,
    telegram_notifier=None,
    interval_str: str = "15m",
    buffer_sec: int = 5,
    poll_sec: int = 10
) -> float:
    """
    Sleeps until the next candle boundary (:00, :15, :30, :45) plus a buffer (in seconds).
    Actively checks for and cancels orphan SL/TP orders (OCO watchdog) every poll_sec seconds.
    Ensures that candle data on Binance is fully finalized before evaluating signals.
    """
    candle_seconds = get_interval_seconds(interval_str)
    now_ts = time.time()
    next_boundary = ((int(now_ts) // candle_seconds) + 1) * candle_seconds + buffer_sec
    sleep_sec = next_boundary - now_ts
    if sleep_sec <= 0:
        sleep_sec += candle_seconds

    next_time_str = datetime.fromtimestamp(next_boundary).strftime('%H:%M:%S')
    mins, secs = int(sleep_sec // 60), int(sleep_sec % 60)
    logger.info(f"⏳ Waiting {mins}m {secs}s for next candle close @ {next_time_str} (OCO Watchdog active)...")

    while True:
        now = time.time()
        remaining = next_boundary - now
        if remaining <= 0:
            break

        step = min(float(poll_sec), remaining)
        time.sleep(step)

        if next_boundary - time.time() <= 0:
            break

        # OCO Watchdog: check if any position closed and cancel lingering opposite orders
        if order_manager:
            try:
                cancelled = order_manager.reconcile_orphan_orders()
                if cancelled and telegram_notifier:
                    for c in cancelled:
                        telegram_notifier.alert_order_reconciled(c["symbol"], c["type"], c["orderId"])
            except Exception as e:
                logger.debug(f"Watchdog reconcile check error: {e}")

    return sleep_sec


# ─────────────────────────────────────────────
#  Init
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("🚀 Binance Futures Intraday Multi-Pair Bot starting...")
    logger.info(f"Pairs: {', '.join(SYMBOLS)} | Timeframe: {cfg.TIMEFRAME} | Testnet: {cfg.USE_TESTNET}")

    if "--backtest" in sys.argv:
        run_backtest()
        sys.exit(0)

    # Initialize modules
    order_mgr = OrderManager(cfg.API_KEY, cfg.API_SECRET, cfg.USE_TESTNET)
    risk_mgr = RiskManager(CONFIG)
    telegram = TelegramNotifier(cfg.TELEGRAM_BOT_TOKEN, cfg.TELEGRAM_CHAT_ID)

    symbols_display = ", ".join(SYMBOLS)
    telegram.alert_startup(symbols_display, cfg.TIMEFRAME, cfg.USE_TESTNET)

    # Check if startup is fresh (within 60 seconds of candle close)
    candle_sec = get_interval_seconds(cfg.TIMEFRAME)
    elapsed_into_candle = int(time.time()) % candle_sec

    if elapsed_into_candle <= 60:
        logger.info(f"⚡ Fresh candle detected ({elapsed_into_candle}s into new candle). Running immediately...")
        run_strategy()
    else:
        mins_late = elapsed_into_candle // 60
        secs_late = elapsed_into_candle % 60
        logger.info(
            f"⚠️ Bot started mid-candle ({mins_late}m {secs_late}s late). "
            f"Waiting for next candle close to prevent entry slippage."
        )

    logger.info("Bot running in candle-aligned mode. Press Ctrl+C to stop.")
    try:
        while True:
            sleep_until_next_candle(order_mgr, telegram, cfg.TIMEFRAME, buffer_sec=5, poll_sec=10)
            run_strategy()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")

