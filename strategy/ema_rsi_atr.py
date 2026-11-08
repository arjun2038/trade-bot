"""
strategy/ema_rsi_atr.py
Computes all technical indicators and generates trade signals.
Implements EMA crossover + RSI filter + ATR-based risk management.
Pure pandas/numpy — no external TA library required.
"""

import pandas as pd
import numpy as np
from utils.logger import get_logger

logger = get_logger("strategy")


# ─────────────────────────────────────────────
#  Indicator calculations
# ─────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def volume_ma(series: pd.Series, period: int = 20) -> pd.Series:
    """Simple moving average of volume."""
    return series.rolling(window=period).mean()


# ─────────────────────────────────────────────
#  Signal generation
# ─────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Add all indicator columns to the OHLCV DataFrame.

    Args:
        df:  OHLCV DataFrame from fetcher
        cfg: Config dict with indicator periods

    Returns:
        DataFrame with added indicator columns
    """
    df = df.copy()
    df["ema_fast"] = ema(df["close"], cfg["EMA_FAST"])
    df["ema_slow"] = ema(df["close"], cfg["EMA_SLOW"])
    df["rsi"] = rsi(df["close"], cfg["RSI_PERIOD"])
    df["atr"] = atr(df, cfg["ATR_PERIOD"])
    df["vol_ma"] = volume_ma(df["volume"], cfg["VOLUME_MA_PERIOD"])
    return df


def generate_signal(df: pd.DataFrame, cfg: dict) -> dict:
    """
    Analyze the latest candle and return a trade signal.

    Returns a dict:
        {
          "signal":     "long" | "short" | "none",
          "entry":      float,
          "stop_loss":  float,
          "take_profit": float,
          "atr":        float,
          "rsi":        float,
          "reason":     str
        }
    """
    df = compute_indicators(df, cfg)

    # Use second-to-last candle (last closed candle — not the forming one)
    if len(df) < cfg["EMA_SLOW"] + 5:
        return _no_signal("Not enough candles for indicators")

    prev = df.iloc[-3]   # Two candles ago
    curr = df.iloc[-2]   # Last closed candle

    ema_cross_up   = prev["ema_fast"] <= prev["ema_slow"] and curr["ema_fast"] > curr["ema_slow"]
    ema_cross_down = prev["ema_fast"] >= prev["ema_slow"] and curr["ema_fast"] < curr["ema_slow"]
    volume_ok      = curr["volume"] > curr["vol_ma"]
    rsi_bullish    = curr["rsi"] > 50
    rsi_bearish    = curr["rsi"] < 50

    entry = curr["close"]
    atr_val = curr["atr"]
    sl_dist = atr_val * cfg["ATR_SL_MULTIPLIER"]
    tp_dist = atr_val * cfg["ATR_TP_MULTIPLIER"]

    if ema_cross_up and rsi_bullish and volume_ok:
        return {
            "signal": "long",
            "entry": entry,
            "stop_loss": entry - sl_dist,
            "take_profit": entry + tp_dist,
            "atr": atr_val,
            "rsi": round(curr["rsi"], 2),
            "reason": f"EMA crossover UP | RSI={curr['rsi']:.1f} | Vol confirmed"
        }

    if ema_cross_down and rsi_bearish and volume_ok:
        return {
            "signal": "short",
            "entry": entry,
            "stop_loss": entry + sl_dist,
            "take_profit": entry - tp_dist,
            "atr": atr_val,
            "rsi": round(curr["rsi"], 2),
            "reason": f"EMA crossover DOWN | RSI={curr['rsi']:.1f} | Vol confirmed"
        }

    return _no_signal(
        f"No crossover | EMA_fast={curr['ema_fast']:.2f} EMA_slow={curr['ema_slow']:.2f} "
        f"RSI={curr['rsi']:.1f} Vol_ok={volume_ok}"
    )


def _no_signal(reason: str) -> dict:
    return {
        "signal": "none",
        "entry": None,
        "stop_loss": None,
        "take_profit": None,
        "atr": None,
        "rsi": None,
        "reason": reason
    }

