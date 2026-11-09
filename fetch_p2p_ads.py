"""
fetch_p2p_ads.py
Fetches live public P2P advertisements on Binance in real time.
Supports filtering by fiat (INR, USD, etc.), trade type (BUY/SELL),
budget/amount, and payment method (UPI, IMPS, Paytm, etc.).

Usage:
    python fetch_p2p_ads.py                      # Top INR ads for buying USDT
    python fetch_p2p_ads.py --amount 500         # Filter for ads accepting ₹500
    python fetch_p2p_ads.py --pay UPI            # Filter by payment method
    python fetch_p2p_ads.py --fiat USD           # Filter by another fiat currency
"""

import argparse
import requests
import json


def fetch_p2p_advertisements(
    asset: str = "USDT",
    fiat: str = "INR",
    trade_type: str = "BUY",
    trans_amount: str = None,
    pay_types: list = None,
    rows: int = 10,
    merchant_only: bool = True
) -> list:
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    payload = {
        "asset": asset,
        "fiat": fiat,
        "merchantCheck": merchant_only,
        "page": 1,
        "payTypes": pay_types or [],
        "publisherType": "merchant" if merchant_only else None,
        "rows": rows,
        "tradeType": trade_type
    }
    if trans_amount:
        payload["transAmount"] = str(trans_amount)

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data
    except Exception as e:
        print(f"Error fetching P2P advertisements: {e}")
        return []


def display_p2p_ads(ads: list, asset: str, fiat: str, trade_type: str, amount_filter: str = None):
    action = f"BUY {asset}" if trade_type == "BUY" else f"SELL {asset}"
    filter_label = f" | Filter: {amount_filter} {fiat}" if amount_filter else ""
    print("\n" + "=" * 95)
    print(f"            LIVE BINANCE P2P MARKET: {action} ({fiat}){filter_label}")
    print("=" * 95)

    if not ads:
        print("No advertisements found matching the given criteria.")
        print("=" * 95 + "\n")
        return

    print(f"{'#':<3} | {'Merchant':<18} | {'Price':<12} | {'Limits (Min - Max)':<26} | {'Pay Methods':<15} | {'Finish Rate'}")
    print("-" * 95)

    for idx, item in enumerate(ads, 1):
        adv = item.get("adv", {})
        advertiser = item.get("advertiser", {})

        name = advertiser.get("nickName", "Unknown")[:16]
        price = f"{float(adv.get('price', 0)):,.2f} {fiat}"
        min_limit = float(adv.get("minSingleTransAmount", 0))
        max_limit = float(adv.get("maxSingleTransAmount", 0))
        limits_str = f"₹{min_limit:,.0f} - ₹{max_limit:,.0f}" if fiat == "INR" else f"{min_limit:,.0f} - {max_limit:,.0f} {fiat}"
        
        methods = [m.get("tradeMethodName") for m in adv.get("tradeMethods", []) if m.get("tradeMethodName")]
        methods_str = ", ".join(methods[:2])
        if len(methods) > 2:
            methods_str += f" +{len(methods)-2}"

        orders_count = advertiser.get("monthOrderCount", 0)
        finish_rate = advertiser.get("monthFinishRate", 0) * 100
        rate_str = f"{finish_rate:.1f}% ({orders_count} orders)"

        adv_no = adv.get("advNo")
        direct_url = f"https://c2c.binance.com/en/fiatOrder?advNo={adv_no}"
        print(f"{idx:<3} | {name:<18} | {price:<12} | {limits_str:<26} | {methods_str:<15} | {rate_str}")
        print(f"    👉 Direct Buy Link: {direct_url}")

    print("=" * 95 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Binance P2P Live Advertisements")
    parser.add_argument("--fiat", default="INR", help="Fiat currency (e.g. INR, USD)")
    parser.add_argument("--asset", default="USDT", help="Crypto asset (e.g. USDT, BTC)")
    parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"], help="Trade side")
    parser.add_argument("--amount", default=None, help="Specific transaction amount to filter")
    parser.add_argument("--pay", default=None, help="Payment method (e.g. UPI, IMPS, Paytm)")
    parser.add_argument("--max-min-limit", type=float, default=15000.0, help="Exclude merchants requiring >= this minimum order (default 15000)")
    parser.add_argument("--limit", type=int, default=10, help="Number of ads to display")

    args = parser.parse_args()
    pay_list = [args.pay] if args.pay else []

    ads = fetch_p2p_advertisements(
        asset=args.asset,
        fiat=args.fiat,
        trade_type=args.side,
        trans_amount=args.amount,
        pay_types=pay_list,
        rows=args.limit * 2
    )

    # Filter out orders where minimum limit is >= max_min_limit, and exclude restricted KYC requirements
    filtered_ads = []
    for a in ads:
        adv = a.get("adv", {})
        min_limit = float(adv.get("minSingleTransAmount", 0))
        if args.max_min_limit is not None and min_limit >= args.max_min_limit:
            continue
        # Exclude ads requiring additional KYC (causes "Restricted" status)
        if adv.get("takerAdditionalKycRequired", 0) != 0:
            continue
        # Exclude counterparty barriers
        if adv.get("buyerRegDaysLimit") or adv.get("buyerBtcPositionLimit") or adv.get("buyerKycLimit"):
            continue
        filtered_ads.append(a)

    display_p2p_ads(filtered_ads[:args.limit], args.asset, args.fiat, args.side, args.amount)
