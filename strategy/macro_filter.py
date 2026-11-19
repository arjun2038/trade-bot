"""
strategy/macro_filter.py
Monitors higher-timeframe market regime across Bitcoin (BTC) and Ethereum (ETH).
Provides macro trend alignment to ensure altcoin intraday trades align with the market tide.
"""

import pandas as pd
from data.fetcher import fetch_ohlcv
from utils.logger import get_logger

logger = get_logger("macro_filter")

# Cache to avoid excessive API calls within the same cycle
_cached_regime = None
_last_fetch_time = 0


def calculate_ema(series: pd.Series, period: int = 50) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def get_macro_regime(use_testnet: bool = False, timeframe: str = "4h", period: int = 50) -> dict:
    """
    Check whether BTC and ETH are in a Bull or Bear regime on the higher timeframe (default 4H).

    Returns dict:
        {
            "regime": "bull" | "bear" | "neutral",
            "btc_bull": bool,
            "eth_bull": bool,
            "btc_price": float,
            "btc_ema": float,
            "eth_price": float,
            "eth_ema": float,
            "summary": str
        }
    """
    global _cached_regime, _last_fetch_time
    import time
    now = time.time()
    # Cache regime for 60 seconds
    if _cached_regime and (now - _last_fetch_time) < 60:
        return _cached_regime

    try:
        btc_df = fetch_ohlcv("BTCUSDT", interval=timeframe, limit=period + 10, use_testnet=use_testnet)
        eth_df = fetch_ohlcv("ETHUSDT", interval=timeframe, limit=period + 10, use_testnet=use_testnet)

        if btc_df.empty or eth_df.empty or len(btc_df) < period or len(eth_df) < period:
            logger.warning("Could not fetch sufficient 4H data for BTC/ETH macro check.")
            return _default_regime("Insufficient macro candle data")

        # Compute 4H EMA 50
        btc_ema = calculate_ema(btc_df["close"], period)
        eth_ema = calculate_ema(eth_df["close"], period)

        btc_curr_price = btc_df["close"].iloc[-1]
        btc_curr_ema = btc_ema.iloc[-1]
        btc_bull = btc_curr_price >= btc_curr_ema

        eth_curr_price = eth_df["close"].iloc[-1]
        eth_curr_ema = eth_ema.iloc[-1]
        eth_bull = eth_curr_price >= eth_curr_ema

        if btc_bull and eth_bull:
            regime = "bull"
            summary = (
                f"BULL REGIME (BTC: ${btc_curr_price:,.1f} > EMA50 ${btc_curr_ema:,.1f} | "
                f"ETH: ${eth_curr_price:,.1f} > EMA50 ${eth_curr_ema:,.1f}) — LONGS ALLOWED"
            )
        elif (not btc_bull) and (not eth_bull):
            regime = "bear"
            summary = (
                f"BEAR REGIME (BTC: ${btc_curr_price:,.1f} < EMA50 ${btc_curr_ema:,.1f} | "
                f"ETH: ${eth_curr_price:,.1f} < EMA50 ${eth_curr_ema:,.1f}) — SHORTS ALLOWED"
            )
        else:
            regime = "neutral"
            summary = (
                f"NEUTRAL / CONFLICT REGIME (BTC {'BULL' if btc_bull else 'BEAR'} vs "
                f"ETH {'BULL' if eth_bull else 'BEAR'}) — CAUTION / FILTER ACTIVE"
            )

        res = {
            "regime": regime,
            "btc_bull": btc_bull,
            "eth_bull": eth_bull,
            "btc_price": btc_curr_price,
            "btc_ema": btc_curr_ema,
            "eth_price": eth_curr_price,
            "eth_ema": eth_curr_ema,
            "summary": summary
        }
        _cached_regime = res
        _last_fetch_time = now
        logger.info(f"[MACRO TIDE] {summary}")
        return res

    except Exception as e:
        logger.error(f"Error checking macro regime: {e}")
        return _default_regime(f"Error: {e}")


def _default_regime(reason: str) -> dict:
    return {
        "regime": "neutral",
        "btc_bull": False,
        "eth_bull": False,
        "btc_price": 0.0,
        "btc_ema": 0.0,
        "eth_price": 0.0,
        "eth_ema": 0.0,
        "summary": f"Neutral fallback ({reason})"
    }
