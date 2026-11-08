"""
backtest/backtester.py
Simple event-driven backtester for the EMA + RSI + ATR strategy.
Runs on historical OHLCV data and reports performance metrics.
"""

import csv
import os
from datetime import datetime
import pandas as pd
from strategy.ema_rsi_atr import compute_indicators, generate_signal
from utils.logger import get_logger

logger = get_logger("backtester")


class Backtester:
    def __init__(self, cfg: dict, initial_balance: float = 10000.0):
        self.cfg = cfg
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.trades = []
        self.open_trade = None

    def run(self, df: pd.DataFrame) -> dict:
        """
        Run backtest on a full OHLCV DataFrame.
        Simulates candle-by-candle execution.
        """
        logger.info(f"Starting backtest on {len(df)} candles...")
        df = compute_indicators(df, self.cfg)

        for i in range(self.cfg["EMA_SLOW"] + 5, len(df)):
            window = df.iloc[:i + 1]
            candle = df.iloc[i]

            # Check if open trade hit SL or TP
            if self.open_trade:
                self._check_exit(candle)

            # Only enter new trade if no open position
            if not self.open_trade:
                signal = generate_signal(window, self.cfg)
                if signal["signal"] != "none":
                    self._enter_trade(signal, candle)

        # Force close any remaining open trade at end
        if self.open_trade:
            self._force_close(df.iloc[-1])

        return self._summary()

    def _enter_trade(self, signal: dict, candle: pd.Series):
        """Record a trade entry."""
        risk_amount = self.balance * self.cfg["RISK_PER_TRADE"] / 100
        sl_dist = abs(signal["entry"] - signal["stop_loss"])
        quantity = risk_amount / sl_dist if sl_dist > 0 else 0

        self.open_trade = {
            "direction": signal["signal"],
            "entry": signal["entry"],
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"],
            "quantity": quantity,
            "open_time": candle.name,
            "reason": signal["reason"],
        }
        logger.debug(f"[{candle.name}] ENTER {signal['signal'].upper()} @ {signal['entry']}")

    def _check_exit(self, candle: pd.Series):
        """Check if SL or TP was hit on this candle."""
        t = self.open_trade
        direction = t["direction"]
        pnl = None

        if direction == "long":
            if candle["low"] <= t["stop_loss"]:
                pnl = (t["stop_loss"] - t["entry"]) * t["quantity"]
                exit_price = t["stop_loss"]
                exit_reason = "SL"
            elif candle["high"] >= t["take_profit"]:
                pnl = (t["take_profit"] - t["entry"]) * t["quantity"]
                exit_price = t["take_profit"]
                exit_reason = "TP"
        else:  # short
            if candle["high"] >= t["stop_loss"]:
                pnl = (t["entry"] - t["stop_loss"]) * t["quantity"]
                exit_price = t["stop_loss"]
                exit_reason = "SL"
            elif candle["low"] <= t["take_profit"]:
                pnl = (t["entry"] - t["take_profit"]) * t["quantity"]
                exit_price = t["take_profit"]
                exit_reason = "TP"

        if pnl is not None:
            self._close_trade(exit_price, pnl, exit_reason, candle.name)

    def _force_close(self, candle: pd.Series):
        """Close at last candle's close price."""
        t = self.open_trade
        if t["direction"] == "long":
            pnl = (candle["close"] - t["entry"]) * t["quantity"]
        else:
            pnl = (t["entry"] - candle["close"]) * t["quantity"]
        self._close_trade(candle["close"], pnl, "EOD", candle.name)

    def _close_trade(self, exit_price: float, pnl: float, reason: str, close_time):
        t = self.open_trade
        self.balance += pnl
        trade_record = {
            "open_time": t["open_time"],
            "close_time": close_time,
            "direction": t["direction"],
            "entry": t["entry"],
            "exit": exit_price,
            "sl": t["stop_loss"],
            "tp": t["take_profit"],
            "qty": round(t["quantity"], 6),
            "pnl": round(pnl, 2),
            "balance": round(self.balance, 2),
            "exit_reason": reason,
        }
        self.trades.append(trade_record)
        logger.debug(f"[{close_time}] EXIT {reason} | PnL: ${pnl:.2f} | Balance: ${self.balance:.2f}")
        self.open_trade = None

    def _summary(self) -> dict:
        """Compute and return performance metrics."""
        if not self.trades:
            return {"error": "No trades executed"}

        df = pd.DataFrame(self.trades)
        total = len(df)
        wins = len(df[df["pnl"] > 0])
        losses = len(df[df["pnl"] <= 0])
        win_rate = wins / total * 100 if total > 0 else 0
        total_pnl = df["pnl"].sum()
        max_dd = self._max_drawdown(df["balance"].tolist())
        avg_win = df[df["pnl"] > 0]["pnl"].mean() if wins > 0 else 0
        avg_loss = df[df["pnl"] <= 0]["pnl"].mean() if losses > 0 else 0

        summary = {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "final_balance": round(self.balance, 2),
            "return_pct": round((self.balance - self.initial_balance) / self.initial_balance * 100, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0,
        }

        # Save trades to CSV
        log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "backtest_trades.csv")
        df.to_csv(log_path, index=False)
        logger.info(f"Backtest trades saved to {log_path}")

        return summary

    def _max_drawdown(self, balances: list) -> float:
        """Calculate maximum drawdown percentage."""
        peak = balances[0]
        max_dd = 0.0
        for b in balances:
            if b > peak:
                peak = b
            dd = (peak - b) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return max_dd

