"""
test_order.py
Quick test script to verify:
1. API connection & authentication
2. USDT wallet balance
3. Setting leverage
4. Placing a minimal Market Order
5. Setting Stop Loss & Take Profit orders
6. Cancelling open orders / closing the position safely
"""

import time
import config as cfg
from execution.order_manager import OrderManager
from data.fetcher import fetch_ohlcv
from utils.logger import get_logger

logger = get_logger("test_order")


def run_test():
    symbol = cfg.SYMBOL.replace("/", "").replace(":USDT", "")
    print(f"\n{'='*55}")
    print(f"  🧪 BINANCE FUTURES ORDER TEST")
    print(f"  Symbol:   {symbol}")
    print(f"  Testnet:  {cfg.USE_TESTNET}")
    print(f"{'='*55}\n")

    order_mgr = OrderManager(cfg.API_KEY, cfg.API_SECRET, cfg.USE_TESTNET)

    # 1. Check Balance
    print("[1/6] 🔍 Checking USDT balance...")
    balance = order_mgr.get_balance()
    print(f"       Available Balance: {balance:.2f} USDT")
    if balance <= 0:
        print("       ❌ Error: Balance is 0 or failed to authenticate.")
        print("       Please check your API key & secret in .env")
        return

    # 2. Check Precision rules
    print(f"[2/6] 📐 Fetching symbol precision for {symbol}...")
    prec = order_mgr.get_symbol_precision(symbol)
    print(f"       Quantity precision: {prec['quantityPrecision']} decimals")
    print(f"       Price precision:    {prec['pricePrecision']} decimals")

    # 3. Set Leverage
    print(f"[3/6] ⚙️  Setting leverage to {cfg.LEVERAGE}x...")
    order_mgr.set_leverage(symbol, cfg.LEVERAGE)

    # 4. Get current price
    df = fetch_ohlcv(symbol, "1m", limit=5, use_testnet=cfg.USE_TESTNET)
    if df.empty:
        print("       ❌ Failed to fetch current price.")
        return
    current_price = df["close"].iloc[-1]
    print(f"       Current price: ${current_price:,.2f}")

    # Determine safe minimal test size (e.g., minimum notional ~6 USDT)
    min_test_notional = 100.0  # $10 test trade
    test_qty = min_test_notional / current_price
    test_qty = order_mgr.round_quantity(symbol, test_qty)
    # Ensure test_qty is at least the stepSize minimum
    if test_qty <= 0:
        test_qty = 10 ** (-prec["quantityPrecision"]) if prec["quantityPrecision"] > 0 else 1
        test_qty = order_mgr.round_quantity(symbol, test_qty)

    print(f"       Calculated test quantity: {test_qty} {symbol.replace('USDT', '')}")

    # Calculate test SL (0.5% below) and TP (0.5% above)
    test_sl = order_mgr.round_price(symbol, current_price * 0.995)
    test_tp = order_mgr.round_price(symbol, current_price * 1.005)

    # 5. Place Test Market Order (BUY)
    print(f"\n[4/6] 🚀 Placing Test BUY Market Order ({test_qty} {symbol})...")
    order_res = order_mgr.place_market_order(symbol, "BUY", test_qty)
    order_id = order_res.get("orderId")

    if not order_id:
        print("       ❌ Market order failed. Check logs above.")
        return
    print(f"       ✅ Market Order SUCCESS! Order ID: {order_id}")

    # 6. Place Test Stop-Loss & Take-Profit
    print(f"\n[5/6] 🛡️  Placing Stop-Loss at ${test_sl} and Take-Profit at ${test_tp}...")
    sl_res = order_mgr.place_stop_loss(symbol, "SELL", test_qty, test_sl)
    tp_res = order_mgr.place_take_profit(symbol, "SELL", test_qty, test_tp)

    if sl_res.get("algoId") or sl_res.get("orderId"):
        print(f"       ✅ Stop-Loss placed! ID: {sl_res.get('algoId') or sl_res.get('orderId')}")
    else:
        print(f"       ❌ Stop-Loss failed: {sl_res}")

    if tp_res.get("algoId") or tp_res.get("orderId"):
        print(f"       ✅ Take-Profit placed! ID: {tp_res.get('algoId') or tp_res.get('orderId')}")
    else:
        print(f"       ❌ Take-Profit failed: {tp_res}")

    # Verify Open Positions
    open_pos = order_mgr.get_open_positions(symbol)
    print(f"\n       Active open positions: {len(open_pos)}")
    for p in open_pos:
        print(f"       -> Qty: {p.get('positionAmt')}, Entry: {p.get('entryPrice')}, Unrealized PnL: {p.get('unRealizedProfit')}")

    # 7. Clean up (Optional auto-close test trade)
    print(f"\n[6/6] 🧹 Clean up:")
    answer = input("\nDo you want to close this test position and cancel open SL/TP orders now? (y/n): ").strip().lower()
    if answer == "y":
        print("       Cancelling SL and TP orders...")
        order_mgr.cancel_all_orders(symbol)
        print(f"       Closing position with SELL MARKET order ({test_qty})...")
        order_mgr.place_market_order(symbol, "SELL", test_qty, reduce_only=True)
        print("       ✅ Position closed and orders cleared cleanly!")
    else:
        print("       ℹ️ Position left open. You can close it manually or wait for SL/TP.")

    print(f"\n{'='*55}")
    print("  🎉 ORDER LOGIC TEST COMPLETE")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    run_test()

