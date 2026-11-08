import requests
import pandas as pd
from datetime import datetime
from backtest.backtester import Backtester
import config as cfg

months = [
    ('Jan 2026', datetime(2026, 1, 1), datetime(2026, 2, 1)),
    ('Feb 2026', datetime(2026, 2, 1), datetime(2026, 3, 1)),
    ('Mar 2026', datetime(2026, 3, 1), datetime(2026, 4, 1)),
    ('Apr 2026', datetime(2026, 4, 1), datetime(2026, 5, 1)),
    ('May 2026', datetime(2026, 5, 1), datetime(2026, 6, 1)),
    ('Jun 2026', datetime(2026, 6, 1), datetime(2026, 7, 1)),
    ('Jul 2026', datetime(2026, 7, 1), datetime(2026, 8, 1)),
    ('Aug 2026', datetime(2026, 8, 1), datetime(2026, 9, 1)),
    ('Sep 2026', datetime(2026, 9, 1), datetime(2026, 10, 1)),
    ('Oct 2026', datetime(2026, 10, 1), datetime(2026, 11, 1)),
]

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

print(f"{'Month':<10} | {'Investment':<10} | {'Net PnL':<12} | {'Return %':<10} | {'End Balance':<12} | {'Trades':<6} | {'Win Rate':<8}")
print('-' * 82)

total_pnl = 0.0

for name, s_dt, e_dt in months:
    start_time = int(s_dt.timestamp() * 1000)
    end_time = int(e_dt.timestamp() * 1000)
    all_klines = []
    cur_start = start_time
    while cur_start < end_time:
        url = f'https://fapi.binance.com/fapi/v1/klines?symbol=XRPUSDT&interval=15m&startTime={cur_start}&endTime={end_time}&limit=1500'
        resp = requests.get(url).json()
        if not resp or not isinstance(resp, list):
            break
        all_klines.extend(resp)
        cur_start = resp[-1][6] + 1
        if len(resp) < 1500:
            break

    if not all_klines:
        continue

    df = pd.DataFrame(all_klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'num_trades',
        'taker_buy_base_vol', 'taker_buy_quote_vol', 'ignore'
    ])
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    df = df[~df.index.duplicated(keep='first')]

    bt = Backtester(CONFIG, initial_balance=100.0)
    res = bt.run(df)

    ret_pct = res.get('return_pct', 0.0)
    pnl = res.get('total_pnl', 0.0)
    final_bal = res.get('final_balance', 100.0)
    trades = res.get('total_trades', 0)
    win_rate = res.get('win_rate_pct', 0.0)
    total_pnl += pnl

    print(f"{name:<10} | $100.00    | {pnl:+9.2f} $  | {ret_pct:+7.2f}%   | ${final_bal:<10.2f} | {trades:<6} | {win_rate:5.1f}%")

print('-' * 82)
print(f"Total Net PnL across 10 individual months: {total_pnl:+.2f} USDT")

