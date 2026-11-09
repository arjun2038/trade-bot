"""
p2p_price_alert.py
Continuously monitors Binance P2P market for BUY USDT ads matching target price and limit conditions.
Features:
- Live polling every N seconds
- Sound chime on Windows when a match is found
- Telegram notification alert (if configured in .env)
- Filters by price <= target (e.g. <= 102.50 INR)
- Filters by minimum & maximum allowable purchase amount
- Direct link to trade on Binance P2P
"""

import os
import sys
import time
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv

# Try importing winsound for audio alerts on Windows
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# Load environment variables for Telegram
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def send_telegram_alert(msg: str):
    """Send an alert to Telegram if configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[Telegram Error] {e}")


def play_sound():
    """Play an alert beep on Windows."""
    if HAS_WINSOUND:
        try:
            for _ in range(3):
                winsound.Beep(1200, 200)
                time.sleep(0.05)
        except Exception:
            pass


def fetch_p2p_page(
    asset: str = "USDT",
    fiat: str = "INR",
    trade_type: str = "BUY",
    page: int = 1,
    rows: int = 20,
    pay_types: list = None,
    merchant_only: bool = True
) -> list:
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    payload = {
        "asset": asset,
        "fiat": fiat,
        "merchantCheck": merchant_only,
        "page": page,
        "payTypes": pay_types or [],
        "publisherType": "merchant" if merchant_only else None,
        "rows": rows,
        "tradeType": trade_type
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=8)
        if resp.status_code == 200:
            return resp.json().get("data", [])
    except Exception:
        pass
    return []


def monitor_p2p(
    max_price: float = 102.50,
    min_purchase: float = 100.0,
    max_min_limit: float = 15000.0,
    fiat: str = "INR",
    asset: str = "USDT",
    poll_interval: int = 5,
    max_pages: int = 3,
    merchant_only: bool = True
):
    print("=" * 80)
    print("          🚀 BINANCE P2P REAL-TIME PRICE MONITOR STARTED")
    print("=" * 80)
    print(f"• Target Asset / Fiat:  {asset} / {fiat}")
    print(f"• Target Max Price:     <= {max_price:.2f} {fiat}")
    print(f"• Purchase Capacity:    Can buy >= {min_purchase:.0f} {fiat}")
    if max_min_limit is not None:
        print(f"• Exclude Min Orders:   Merchant min limit must be < {max_min_limit:,.0f} {fiat} (>= {max_min_limit:,.0f} ignored)")
    print(f"• Exclude Restricted:   {'Yes (Verified PRO Merchants Only - No Restrictions)' if merchant_only else 'No'}")
    print(f"• Refresh Interval:     Every {poll_interval}s across top {max_pages} pages")
    print(f"• Audio Alerts:         {'Enabled (Windows Beep)' if HAS_WINSOUND else 'Disabled'}")
    print(f"• Telegram Alerts:      {'Enabled' if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else 'Disabled'}")
    print("=" * 80)
    print("Scanning market... Press Ctrl+C to stop.\n")

    seen_adv_nos = set()
    scan_count = 0

    try:
        while True:
            scan_count += 1
            now_str = datetime.now().strftime("%H:%M:%S")
            all_ads = []

            for p in range(1, max_pages + 1):
                page_ads = fetch_p2p_page(
                    asset=asset, fiat=fiat, trade_type="BUY", page=p, rows=20, merchant_only=merchant_only
                )
                if not page_ads:
                    break
                all_ads.extend(page_ads)

            # Filter matching deals
            matches = []
            cheapest_in_market = float("inf")

            for item in all_ads:
                adv = item.get("adv", {})
                price = float(adv.get("price", 0))
                min_limit = float(adv.get("minSingleTransAmount", 0))
                max_limit = float(adv.get("maxSingleTransAmount", 0))

                if price < cheapest_in_market:
                    cheapest_in_market = price

                # Exclude non-tradable or abnormal status
                if adv.get("isTradable") is False or adv.get("abnormalStatusList"):
                    continue

                # Exclude ads requiring additional KYC (Causes the "Restricted" button in Binance!)
                if adv.get("takerAdditionalKycRequired", 0) != 0:
                    continue

                # Exclude counterparty barriers (minimum account age, minimum BTC holding requirements)
                if adv.get("buyerRegDaysLimit") or adv.get("buyerBtcPositionLimit") or adv.get("buyerKycLimit"):
                    continue

                # Price condition: <= max_price
                if price > max_price:
                    continue

                # Must allow purchasing >= min_purchase (i.e. maximum transaction limit is at least min_purchase)
                if max_limit < min_purchase:
                    continue

                # Exclude orders where required minimum is 15,000 RS or more
                if max_min_limit is not None and min_limit >= max_min_limit:
                    continue

                matches.append(item)

            # Display progress status
            if not matches:
                sys.stdout.write(
                    f"\r[{now_str}] Check #{scan_count}: No active ad <= {max_price:.2f} {fiat} | Cheapest verified: {cheapest_in_market:.2f} {fiat} | Scanned {len(all_ads)} ads"
                )
                sys.stdout.flush()
            else:
                print(f"\n\n🔥 [{now_str}] MATCH FOUND! ({len(matches)} ads matching <= {max_price:.2f} {fiat}):")
                play_sound()

                for m in matches:
                    adv = m.get("adv", {})
                    advertiser = m.get("advertiser", {})
                    adv_no = adv.get("advNo")
                    price = float(adv.get("price", 0))
                    min_lim = float(adv.get("minSingleTransAmount", 0))
                    max_lim = float(adv.get("maxSingleTransAmount", 0))
                    nick = advertiser.get("nickName", "Unknown")
                    user_no = advertiser.get("userNo", "")
                    orders = advertiser.get("monthOrderCount", 0)
                    finish_rate = advertiser.get("monthFinishRate", 0) * 100
                    methods = [x.get("tradeMethodName") for x in adv.get("tradeMethods", []) if x.get("tradeMethodName")]
                    methods_str = ", ".join(methods[:3])

                    direct_buy_url = f"https://c2c.binance.com/en/fiatOrder?advNo={adv_no}"
                    app_ad_url = f"https://app.binance.com/en/p2p/advertisementDetail?advNo={adv_no}"
                    profile_url = f"https://p2p.binance.com/en/advertiserDetail?userNo={user_no}"

                    print("  " + "-" * 75)
                    print(f"  • Price:         {price:.2f} {fiat}")
                    print(f"  • Merchant:      {nick} (Verified Merchant ⭐ | Completion: {finish_rate:.1f}% | {orders} orders)")
                    print(f"  • Order Limits:  ₹{min_lim:,.0f} to ₹{max_lim:,.0f}")
                    print(f"  • Pay Methods:   {methods_str}")
                    print(f"  • 🔗 DIRECT BUY:  {direct_buy_url}")
                    print(f"  • 📱 APP LINK:   {app_ad_url}")
                    print(f"  • 👤 PROFILE:    {profile_url}")

                    # Notify Telegram if new
                    if adv_no not in seen_adv_nos:
                        seen_adv_nos.add(adv_no)
                        tele_msg = (
                            f"🚨 *P2P DEAL ALERT!* 🚨\n\n"
                            f"*Price:* `{price:.2f} {fiat}`\n"
                            f"*Merchant:* {nick} ({finish_rate:.1f}%)\n"
                            f"*Limits:* ₹{min_lim:,.0f} - ₹{max_lim:,.0f}\n"
                            f"*Methods:* {methods_str}\n\n"
                            f"👉 [DIRECT BUY LINK]({direct_buy_url})\n"
                            f"👉 [OPEN IN BINANCE APP]({app_ad_url})"
                        )
                        send_telegram_alert(tele_msg)

                print("  " + "-" * 75 + "\n")

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\n\nMonitor stopped by user.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Continuous Binance P2P Buy Order Monitor")
    parser.add_argument("--max-price", type=float, default=102.50, help="Maximum price (default 102.50)")
    parser.add_argument("--min-purchase", type=float, default=100.0, help="Must allow purchasing at least this amount (default 100)")
    parser.add_argument("--max-min-limit", type=float, default=15000.0, help="Exclude merchants whose minimum required order is >= this amount (default 15000)")
    parser.add_argument("--interval", type=int, default=5, help="Seconds between polls (default 5)")
    parser.add_argument("--include-unverified", action="store_true", help="Include non-merchant individual ads (which may show as Restricted)")
    parser.add_argument("--fiat", default="INR", help="Fiat currency (default INR)")
    parser.add_argument("--asset", default="USDT", help="Asset (default USDT)")
    parser.add_argument("--pages", type=int, default=3, help="Pages to scan (default 3)")

    args = parser.parse_args()

    monitor_p2p(
        max_price=args.max_price,
        min_purchase=args.min_purchase,
        max_min_limit=args.max_min_limit,
        fiat=args.fiat,
        asset=args.asset,
        poll_interval=args.interval,
        max_pages=args.pages,
        merchant_only=not args.include_unverified
    )

