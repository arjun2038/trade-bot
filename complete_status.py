import config as cfg
from execution.order_manager import OrderManager
from datetime import datetime

om = OrderManager(cfg.API_KEY, cfg.API_SECRET, cfg.USE_TESTNET)

# 1. Fetch entire account / position risk for all symbols
pos_risk = om._get('/fapi/v2/positionRisk', {})
active_positions = []
if isinstance(pos_risk, list):
    for p in pos_risk:
        if float(p.get('positionAmt', 0)) != 0:
            active_positions.append(p)

# 2. Fetch trade execution history
symbols_to_check = ['BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'SOLUSDT']
recent_trades = []
for sym in symbols_to_check:
    t_list = om._get('/fapi/v1/userTrades', {'symbol': sym, 'limit': 10})
    if isinstance(t_list, list):
        recent_trades.extend(t_list)

recent_trades.sort(key=lambda x: x.get('time', 0), reverse=True)

# 3. Fetch recent account income (realized PnL, funding fees, trading fees)
income_stream = om._get('/fapi/v1/income', {'limit': 10})

# 4. Open Orders
open_orders = om._get('/fapi/v1/openOrders', {})

print("\n" + "=" * 65)
print("             COMPLETE BINANCE FUTURES STATUS")
print("=" * 65)

# Balance
balance = om.get_balance()
print(f"Wallet Balance:       {balance:.2f} USDT")
print(f"Environment:          {'TESTNET' if cfg.USE_TESTNET else 'LIVE'}")

print("\n--- [1] ACTIVE OPEN POSITIONS (ALL ASSETS) ---")
if active_positions:
    for p in active_positions:
        amt = float(p.get('positionAmt'))
        side = 'LONG' if amt > 0 else 'SHORT'
        print(f"• Symbol:           {p.get('symbol')}")
        print(f"  Side:             {side} ({amt})")
        print(f"  Entry Price:      ${float(p.get('entryPrice')):,.4f}")
        print(f"  Mark Price:       ${float(p.get('markPrice')):,.4f}")
        print(f"  Unrealized PnL:   {float(p.get('unRealizedProfit')):+.4f} USDT")
        print(f"  Leverage:         {p.get('leverage')}x ({p.get('marginType', 'cross').upper()})")
        print(f"  Liquidation:      ${float(p.get('liquidationPrice', 0)):,.4f}")
else:
    print("No open positions on any asset.")

print("\n--- [2] UNFILLED OPEN ORDERS ---")
if isinstance(open_orders, list) and open_orders:
    for o in open_orders:
        dt = datetime.fromtimestamp(o.get('time', 0) / 1000)
        print(f"• ID: {o.get('orderId')} | {o.get('symbol')} | {o.get('side')} {o.get('origQty')} @ ${o.get('price')} ({o.get('type')}) | Placed: {dt.strftime('%H:%M:%S')}")
else:
    print("No active unfilled limit or trigger orders.")

print("\n--- [3] RECENT EXECUTED TRADES ---")
if recent_trades:
    for t in recent_trades[:8]:
        dt = datetime.fromtimestamp(t.get('time', 0) / 1000)
        pnl = float(t.get('realizedPnl', 0))
        fee = float(t.get('commission', 0))
        print(f"[{dt.strftime('%Y-%m-%d %H:%M:%S')}] {t.get('symbol')} | {t.get('side')} {t.get('qty')} @ ${float(t.get('price')):,.2f} | Realized PnL: {pnl:+.4f} USDT | Fee: {fee:.4f} {t.get('commissionAsset')}")
else:
    print("No recent trades found.")

print("\n--- [4] RECENT ACCOUNT INCOME / REALIZED PNL ---")
if isinstance(income_stream, list) and income_stream:
    for inc in income_stream[:6]:
        dt = datetime.fromtimestamp(inc.get('time', 0) / 1000)
        print(f"[{dt.strftime('%Y-%m-%d %H:%M:%S')}] {inc.get('incomeType'):<18} | {float(inc.get('income')):+.4f} {inc.get('asset')} ({inc.get('symbol', 'ALL')})")
else:
    print("No income entries found.")

print("=" * 65 + "\n")

