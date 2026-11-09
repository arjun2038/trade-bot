import time
import hmac
import hashlib
import requests
from datetime import datetime
import config as cfg


def get_p2p_orders(trade_type: str):
    timestamp = int(time.time() * 1000)
    params = {"tradeType": trade_type, "rows": 10, "timestamp": timestamp}
    query = "&".join([f"{k}={v}" for k, v in params.items()])
    sig = hmac.new(cfg.API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"https://api.binance.com/sapi/v1/c2c/orderMatch/listUserOrderHistory?{query}&signature={sig}"
    headers = {"X-MBX-APIKEY": cfg.API_KEY}
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 200:
        return resp.json().get("data", [])
    return []


if __name__ == "__main__":
    buys = get_p2p_orders("BUY")
    sells = get_p2p_orders("SELL")
    orders = buys + sells
    orders.sort(key=lambda x: x.get("createTime", 0), reverse=True)

    print("\n" + "=" * 80)
    print("                     LATEST BINANCE P2P / C2C ORDERS")
    print("=" * 80)

    if not orders:
        print("No P2P orders found on this account.")
    else:
        for o in orders[:8]:
            dt = datetime.fromtimestamp(o.get("createTime", 0) / 1000)
            t_type = o.get("tradeType")
            status = o.get("orderStatus")
            asset = o.get("asset")
            fiat = o.get("fiat")
            amt = float(o.get("amount", 0))
            total = float(o.get("totalPrice", 0))
            unit_price = float(o.get("unitPrice", 0))
            counterpart = o.get("counterPartNickName", "N/A")
            pay_method = o.get("payMethodName", "N/A")
            order_id = o.get("orderNumber")

            print(f"[{dt.strftime('%Y-%m-%d %H:%M:%S')}] {t_type:<4} | {amt:,.2f} {asset} @ {unit_price:,.2f} {fiat} (Total: {total:,.2f} {fiat})")
            print(f"   Status: {status:<12} | Merchant: {counterpart:<15} | Pay: {pay_method}")
            print(f"   Order ID: {order_id}")
            print("-" * 80)

    print("=" * 80 + "\n")

