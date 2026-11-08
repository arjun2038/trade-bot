"""
data/fetcher.py
Fetches OHLCV candle data from Binance Futures REST API.
No third-party exchange library required — uses plain requests.
"""

import time
import requests
import pandas as pd
from utils.logger import get_logger

logger = get_logger("fetcher")

# Binance Futures API endpoints
LIVE_BASE_URL = "https://fapi.binance.com"
TESTNET_BASE_URL = "https://testnet.binancefuture.com"


def get_base_url(use_testnet: bool) -> str:
    return TESTNET_BASE_URL if use_testnet else LIVE_BASE_URL


def fetch_ohlcv(symbol: str, interval: str, limit: int = 200, use_testnet: bool = True) -> pd.DataFrame:
    """
    Fetch OHLCV candlestick data from Binance Futures.

    Args:
        symbol:      Trading pair in Binance format e.g. 'BTCUSDT'
        interval:    Timeframe e.g. '15m', '1h', '4h'
        limit:       Number of candles to fetch (max 1500)
        use_testnet: If True, use Binance Futures Testnet

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    base_url = get_base_url(use_testnet)
    endpoint = f"{base_url}/fapi/v1/klines"

    params = {
        "symbol": symbol.replace("/", "").replace(":USDT", ""),  # e.g. BTCUSDT
        "interval": interval,
        "limit": limit,
    }

    # Try fetching up to 3 times, with fallback to live public market data if testnet DNS/network hiccups
    raw = None
    urls_to_try = [
        f"{base_url}/fapi/v1/klines",
        f"{LIVE_BASE_URL}/fapi/v1/klines"  # Live endpoint is public and 99.99% available
    ]

    for url in urls_to_try:
        for attempt in range(1, 4):
            try:
                logger.debug(f"Fetching {limit} {interval} candles for {symbol} (attempt {attempt})...")
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                raw = response.json()
                if raw:
                    break
            except requests.exceptions.RequestException as e:
                logger.warning(f"Fetch failed on {url} (attempt {attempt}/3): {e}")
                time.sleep(1)
        if raw:
            break

    if not raw:
        logger.error(f"Failed to fetch candles for {symbol} from all endpoints.")
        return pd.DataFrame()

    # Parse response — Binance returns a list of lists
    df = pd.DataFrame(raw, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "num_trades",
        "taker_buy_base_vol", "taker_buy_quote_vol", "ignore"
    ])

    # Keep only relevant columns and cast types
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    logger.info(f"Fetched {len(df)} candles. Latest close: {df['close'].iloc[-1]:.2f}")
    return df


def get_account_balance(api_key: str, api_secret: str, use_testnet: bool = True) -> float:
    """
    Fetch USDT balance from Binance Futures account.
    Returns available USDT balance.
    """
    import hmac
    import hashlib

    base_url = get_base_url(use_testnet)
    endpoint = f"{base_url}/fapi/v2/balance"

    timestamp = int(time.time() * 1000)
    params = f"timestamp={timestamp}"
    signature = hmac.new(api_secret.encode(), params.encode(), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": api_key}
    url = f"{endpoint}?{params}&signature={signature}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        balances = response.json()
        for asset in balances:
            if asset["asset"] == "USDT":
                balance = float(asset["availableBalance"])
                logger.info(f"Available USDT balance: {balance:.2f}")
                return balance
    except Exception as e:
        logger.error(f"Failed to fetch balance: {e}")
    return 0.0

