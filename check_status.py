import config as cfg
from execution.order_manager import OrderManager
from data.fetcher import fetch_ohlcv
from strategy.ema_rsi_atr import compute_indicators, generate_signal

symbol = cfg.SYMBOL.replace('/', '').replace(':USDT', '')
om = OrderManager(cfg.API_KEY, cfg.API_SECRET, cfg.USE_TESTNET)

balance = om.get_balance()
positions = om.get_open_positions(symbol)
algo_orders = om._get('/fapi/v1/algoOpenOrders', {'symbol': symbol})
reg_orders = om._get('/fapi/v1/openOrders', {'symbol': symbol})

CONFIG = {
    'EMA_FAST': cfg.EMA_FAST,
    'EMA_SLOW': cfg.EMA_SLOW,
    'RSI_PERIOD': cfg.RSI_PERIOD,
    'ATR_PERIOD': cfg.ATR_PERIOD,
    'VOLUME_MA_PERIOD': cfg.VOLUME_MA_PERIOD,
    'ATR_SL_MULTIPLIER': cfg.ATR_SL_MULTIPLIER,
    'ATR_TP_MULTIPLIER': cfg.ATR_TP_MULTIPLIER,
    'RISK_PER_TRADE': cfg.RISK_PER_TRADE,
    'DAILY_LOSS_LIMIT': cfg.DAILY_LOSS_LIMIT,
    'MAX_OPEN_TRADES': cfg.MAX_OPEN_TRADES,
}

df = fetch_ohlcv(symbol, cfg.TIMEFRAME, limit=50, use_testnet=cfg.USE_TESTNET)
df = compute_indicators(df, CONFIG)
curr = df.iloc[-2]
sig = generate_signal(df, CONFIG)

print("\n" + "=" * 55)
print("             CURRENT ACCOUNT & TRADE STATUS")
print("=" * 55)
print(f"Trading Pair:         {symbol}")
print(f"Network:              {'TESTNET' if cfg.USE_TESTNET else 'LIVE'}")
print(f"Available Balance:    {balance:.2f} USDT")
print(f"Active Positions:     {len(positions)}")

if positions:
    for p in positions:
        print(f"  -> Side: {'LONG' if float(p.get('positionAmt', 0)) > 0 else 'SHORT'}")
        print(f"     Amount:          {p.get('positionAmt')}")
        print(f"     Entry Price:     ${float(p.get('entryPrice', 0)):,.4f}")
        print(f"     Mark Price:      ${float(p.get('markPrice', 0)):,.4f}")
        print(f"     Unrealized PnL:  {float(p.get('unRealizedProfit', 0)):+.2f} USDT")
else:
    print("  -> No active positions currently open.")

print(f"\nActive Open Orders:   {len(reg_orders) if isinstance(reg_orders, list) else 0}")
print(f"Active SL/TP Orders:  {len(algo_orders) if isinstance(algo_orders, list) else 0}")

print("\n" + "-" * 55)
print("             LATEST 15M CANDLE & STRATEGY STATE")
print("-" * 55)
print(f"Last Closed Candle:   {df.index[-2]}")
print(f"Closing Price:        ${curr['close']:,.4f}")
print(f"EMA 9 (Fast):         ${curr['ema_fast']:,.4f}")
print(f"EMA 21 (Slow):        ${curr['ema_slow']:,.4f}")
print(f"RSI (14):             {curr['rsi']:.2f}")
print(f"ATR (Volatility):     ${curr['atr']:,.4f}")
print(f"Current Signal:       {sig['signal'].upper()}")
print(f"Signal Details:       {sig['reason']}")
print("=" * 55 + "\n")

