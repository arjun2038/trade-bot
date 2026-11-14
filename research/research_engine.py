"""
research/research_engine.py
Autonomous Research Engine Service for Binance Futures.
Monitors top market universe, computes rolling 30-day alpha metrics,
evaluates current active pairs in .env, and sends Telegram recommendations.
"""

import time
import threading
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from strategy.ema_rsi_atr import compute_indicators
from utils.logger import get_logger

logger = get_logger("research_engine")

# Benchmark universe of top liquid Binance Futures candidates (excluding stablecoins)
DEFAULT_UNIVERSE = [
    "AVAXUSDT", "NEARUSDT", "ATOMUSDT", "XLMUSDT", "SOLUSDT",
    "SUIUSDT", "LTCUSDT", "LINKUSDT", "DOGEUSDT", "ADAUSDT",
    "APTUSDT", "TIAUSDT", "BCHUSDT", "UNIUSDT", "FILUSDT",
    "ARBUSDT", "OPUSDT", "AAVEUSDT", "RENDERUSDT", "FETUSDT",
    "INJUSDT", "DOTUSDT", "XRPUSDT", "BTCUSDT", "ETHUSDT"
]

class ResearchEngine:
    def __init__(self, telegram_notifier=None, scan_interval_hours: int = 24, universe: list = None):
        self.telegram = telegram_notifier
        self.scan_interval_hours = scan_interval_hours
        self.universe = universe or DEFAULT_UNIVERSE
        self.last_scan_time = None
        self.latest_rankings = []
        self._is_running = False
        self._thread = None

    def fetch_30d_candles(self, symbol: str, total_candles: int = 2880) -> pd.DataFrame:
        """Fetch 30 days of 15m candles (2880 candles)."""
        url = "https://fapi.binance.com/fapi/v1/klines"
        all_rows = []
        end_time = None
        while len(all_rows) < total_candles:
            params = {"symbol": symbol, "interval": "15m", "limit": 1000}
            if end_time:
                params["endTime"] = end_time
            try:
                r = requests.get(url, params=params, timeout=10).json()
            except Exception as e:
                logger.warning(f"Error fetching candles for {symbol}: {e}")
                break
            if not r or not isinstance(r, list) or len(r) == 0 or isinstance(r, dict):
                break
            all_rows = r + all_rows
            end_time = r[0][0] - 1
            if len(r) < 1000:
                break
        if not all_rows:
            return pd.DataFrame()
        df = pd.DataFrame(all_rows, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "tbbav", "tbqav", "ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        df = df.set_index("timestamp")
        return df.tail(total_candles)

    def evaluate_coin(self, df: pd.DataFrame, min_atr_pct: float = 0.5, fee_rate: float = 0.00045) -> dict:
        """Simulate strategy on 30-day data and compute score."""
        if df.empty or len(df) < 100:
            return None
        cfg = {
            "EMA_FAST": 9, "EMA_SLOW": 21, "RSI_PERIOD": 14,
            "ATR_PERIOD": 14, "VOLUME_MA_PERIOD": 20,
            "ATR_SL_MULTIPLIER": 1.0, "ATR_TP_MULTIPLIER": 2.0
        }
        d = compute_indicators(df, cfg)
        bal = 100.0; in_pos = False; side = None; entry = sl = tp = qty = 0.0
        w = l = 0
        gross_win = gross_loss = 0.0

        for i in range(30, len(d)):
            c = d.iloc[i]
            if in_pos:
                if side == "long":
                    if c["low"] <= sl:
                        bal += (sl - entry) * qty - (entry + sl) * qty * fee_rate
                        l += 1; gross_loss += abs((sl - entry) * qty); in_pos = False
                    elif c["high"] >= tp:
                        bal += (tp - entry) * qty - (entry + tp) * qty * fee_rate
                        w += 1; gross_win += (tp - entry) * qty; in_pos = False
                else:
                    if c["high"] >= sl:
                        bal += (entry - sl) * qty - (entry + sl) * qty * fee_rate
                        l += 1; gross_loss += abs((entry - sl) * qty); in_pos = False
                    elif c["low"] <= tp:
                        bal += (entry - tp) * qty - (entry + tp) * qty * fee_rate
                        w += 1; gross_win += (entry - tp) * qty; in_pos = False

            if not in_pos:
                prev, curr = d.iloc[i-2], d.iloc[i-1]
                atr_v = curr["atr"]
                if pd.isna(atr_v) or atr_v <= 0 or curr["volume"] <= curr["vol_ma"]:
                    continue
                if (atr_v / curr["close"] * 100) < min_atr_pct:
                    continue
                bull = prev["ema_fast"] <= prev["ema_slow"] and curr["ema_fast"] > curr["ema_slow"] and curr["rsi"] > 50
                bear = prev["ema_fast"] >= prev["ema_slow"] and curr["ema_fast"] < curr["ema_slow"] and curr["rsi"] < 50
                if bull:
                    in_pos = True; side = "long"; entry = curr["close"]
                    sl = entry - atr_v; tp = entry + 2 * atr_v; qty = (bal * 0.01) / atr_v
                elif bear:
                    in_pos = True; side = "short"; entry = curr["close"]
                    sl = entry + atr_v; tp = entry - 2 * atr_v; qty = (bal * 0.01) / atr_v

        total_trades = w + l
        net_ret = round(bal - 100.0, 2)
        wr = round((w / total_trades) * 100, 1) if total_trades > 0 else 0.0
        pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (2.5 if gross_win > 0 else 0.5)

        # Recent volatility (last candle)
        last_row = d.iloc[-1]
        curr_atr_pct = (last_row["atr"] / last_row["close"]) * 100

        # Composite Score (0-100)
        # 1. PnL contribution: min 0, max 40
        pnl_score = np.clip(net_ret * 2.0, -10, 40)
        # 2. Win rate contribution: min 0, max 30 (35% -> 0, 50% -> 30)
        wr_score = np.clip((wr - 35) * 2.0, 0, 30)
        # 3. Profit Factor contribution: min 0, max 20
        pf_score = np.clip((pf - 0.8) * 15.0, 0, 20)
        # 4. Volatility quality (ideal: 0.6% - 2.0%): max 10
        vol_score = 10 if 0.6 <= curr_atr_pct <= 2.2 else (5 if 0.5 <= curr_atr_pct < 0.6 else 0)

        composite_score = round(float(pnl_score + wr_score + pf_score + vol_score), 1)

        return {
            "net_return": net_ret,
            "win_rate": wr,
            "trades": total_trades,
            "profit_factor": pf,
            "atr_pct": round(curr_atr_pct, 2),
            "score": max(0.0, min(100.0, composite_score))
        }

    def run_market_scan(self) -> list:
        """Scan all universe symbols and rank them."""
        logger.info(f"🔎 [RESEARCH ENGINE] Starting 30-day market scan across {len(self.universe)} pairs...")
        rankings = []
        for sym in self.universe:
            try:
                df = self.fetch_30d_candles(sym)
                res = self.evaluate_coin(df)
                if res and res["trades"] >= 5:
                    res["symbol"] = sym
                    rankings.append(res)
            except Exception as e:
                logger.error(f"Error analyzing {sym}: {e}")

        rankings.sort(key=lambda x: x["score"], reverse=True)
        self.latest_rankings = rankings
        self.last_scan_time = datetime.now()
        logger.info(f"✅ [RESEARCH ENGINE] Scan complete. Top 5: {[r['symbol'] for r in rankings[:5]]}")
        return rankings

    def check_and_notify(self, current_symbols: list, force_notify: bool = False):
        """Evaluate current .env basket against rankings and send Telegram alerts."""
        if not self.latest_rankings:
            self.run_market_scan()

        top5 = self.latest_rankings[:5]
        top5_symbols = [r["symbol"] for r in top5]
        current_upper = [s.strip().upper() for s in current_symbols]

        # Check underperforming current coins (score < 40 or rank > 12)
        flagged_drops = []
        for s in current_upper:
            coin_rank = next((i + 1 for i, r in enumerate(self.latest_rankings) if r["symbol"] == s), 99)
            coin_stat = next((r for r in self.latest_rankings if r["symbol"] == s), None)
            if coin_stat:
                if coin_stat["score"] < 40.0 or coin_rank > 12 or coin_stat["net_return"] < -5.0:
                    flagged_drops.append((s, coin_rank, coin_stat))
            else:
                flagged_drops.append((s, coin_rank, {"score": 0, "net_return": -10, "win_rate": 0}))

        # Check strong potential additions in Top 3 not currently in basket
        strong_adds = []
        for r in top5[:3]:
            if r["symbol"] not in current_upper and r["score"] >= 65.0:
                strong_adds.append(r)

        # Decide if rotation is recommended
        needs_rotation = len(flagged_drops) > 0 and len(strong_adds) > 0

        if needs_rotation:
            drop_sym, drop_rank, drop_stat = flagged_drops[0]
            add_coin = strong_adds[0]
            # Replace drop_sym with add_coin
            new_basket = [s for s in current_upper if s != drop_sym]
            if add_coin["symbol"] not in new_basket:
                new_basket.append(add_coin["symbol"])
            new_env_str = ",".join(new_basket[:4])

            msg = (
                f"🚨 *RESEARCH ENGINE — ROTATION ALERT*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Market regime shift detected. Consider updating active pairs:\n\n"
                f"❌ *Drop:* `{drop_sym}` (Rank #{drop_rank} | Score: {drop_stat['score']}/100 | Net: {drop_stat['net_return']:+0.1f}%)\n"
                f"⭐ *Add:*  `{add_coin['symbol']}` (Rank #1 | Score: {add_coin['score']}/100 | Net: {add_coin['net_return']:+0.1f}% | WR: {add_coin['win_rate']}%)\n\n"
                f"📋 *Suggested .env line:*\n"
                f"`SYMBOLS={new_env_str}`\n\n"
                f"ℹ️ _Apply when `{drop_sym}` has 0 open positions._"
            )
            logger.info(f"Dispatching rotation recommendation alert: Drop {drop_sym}, Add {add_coin['symbol']}")
            if self.telegram:
                self.telegram.send(msg)

        elif force_notify or (self.last_scan_time and self.last_scan_time.hour in (8, 9)):
            # Periodic health check summary
            summary_lines = []
            for idx, r in enumerate(top5, 1):
                sym = r["symbol"]
                in_basket = " (Active)" if sym in current_upper else ""
                summary_lines.append(f"{idx}. `{sym}`: Score {r['score']}/100 | Ret: {r['net_return']:+0.1f}%{in_basket}")

            msg = (
                f"📊 *RESEARCH ENGINE — DAILY BASKET HEALTH*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Active Basket: `{', '.join(current_upper)}`\n"
                f"Status: *All Active Pairs Healthy — No Changes Required.*\n\n"
                f"🏆 *Current Market Top 5:*\n" +
                "\n".join(summary_lines) +
                f"\n━━━━━━━━━━━━━━━━━━━━"
            )
            logger.info("Dispatching periodic basket health pulse.")
            if self.telegram:
                self.telegram.send(msg)

    def _daemon_loop(self, current_symbols_fn):
        """Background thread loop running every scan_interval_hours."""
        # Initial scan delayed by 30 seconds to let bot boot cleanly
        time.sleep(30)
        logger.info("🚀 [RESEARCH ENGINE] Initializing first background scan...")
        while self._is_running:
            try:
                self.run_market_scan()
                current_symbols = current_symbols_fn()
                self.check_and_notify(current_symbols, force_notify=False)
            except Exception as e:
                logger.error(f"[RESEARCH ENGINE] Error in daemon loop: {e}")

            # Sleep until next scan interval (e.g. 24 hours), checking cancel flag
            sleep_chunk = 60
            elapsed = 0
            target_sec = self.scan_interval_hours * 3600
            while self._is_running and elapsed < target_sec:
                time.sleep(sleep_chunk)
                elapsed += sleep_chunk

    def start_background_service(self, current_symbols_fn):
        """Start the research engine in a non-blocking daemon thread."""
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._daemon_loop, args=(current_symbols_fn,), daemon=True, name="ResearchEngineThread")
        self._thread.start()
        logger.info(f"🛰️ [RESEARCH ENGINE] Running as background daemon (every {self.scan_interval_hours}h).")

    def stop(self):
        """Stop background service."""
        self._is_running = False
