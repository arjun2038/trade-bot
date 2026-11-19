"""
risk/risk_manager.py
Handles position sizing, daily loss limit checks, and trade guards.
"""

import time
from utils.logger import get_logger

logger = get_logger("risk")


class RiskManager:
    def __init__(self, cfg: dict):
        self.risk_pct = cfg["RISK_PER_TRADE"]          # % of balance to risk
        self.daily_loss_limit = cfg["DAILY_LOSS_LIMIT"] # % max daily loss
        self.max_open = cfg["MAX_OPEN_TRADES"]
        self.starting_balance = None
        self.daily_start_balance = None
        self.cooldown_hours = cfg.get("CONSEC_LOSS_COOLDOWN_HOURS", 12)
        self.symbol_cooldowns = {}  # symbol -> expiry timestamp (float seconds)

    def set_balance(self, balance: float):
        """Call once at startup and each day."""
        if balance <= 0:
            logger.warning(f"Balance reported as {balance:.2f} USDT. Starting balance not initialized.")
            return

        if self.starting_balance is None:
            self.starting_balance = balance
        self.daily_start_balance = balance
        logger.info(f"Balance set: {balance:.2f} USDT")

    def is_daily_loss_hit(self, current_balance: float) -> bool:
        """Returns True if daily loss limit has been exceeded."""
        if self.daily_start_balance is None or self.daily_start_balance <= 0:
            return False
        loss_pct = (self.daily_start_balance - current_balance) / self.daily_start_balance * 100
        if loss_pct >= self.daily_loss_limit:
            logger.warning(f"Daily loss limit hit: {loss_pct:.2f}% >= {self.daily_loss_limit}%")
            return True
        return False

    def calculate_position_size(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        leverage: int
    ) -> float:
        """
        Calculate position size (in contracts/base asset) using fixed-risk model.

        Formula:
            risk_amount = balance * risk_pct / 100
            sl_distance = abs(entry - stop_loss)
            quantity    = risk_amount / sl_distance

        The result is the number of base asset units to trade.
        """
        risk_amount = balance * self.risk_pct / 100
        sl_distance = abs(entry - stop_loss)

        if sl_distance == 0:
            logger.error("Stop loss equals entry price — cannot calculate size")
            return 0.0

        quantity = risk_amount / sl_distance

        # Cap by available margin and leverage (notional value cap)
        # We reserve up to 90% of balance to account for fees and buffer
        max_notional = balance * leverage * 0.90
        max_qty_by_margin = max_notional / entry if entry > 0 else 0

        if quantity > max_qty_by_margin:
            logger.info(
                f"Calculated qty {quantity:.4f} exceeds margin capacity ({max_qty_by_margin:.4f}). "
                f"Capping position to fit available margin with {leverage}x leverage."
            )
            quantity = max_qty_by_margin

        # Round down to 3 decimal places
        quantity = round(quantity, 3)

        logger.info(
            f"Position size: {quantity} | Risk: ${risk_amount:.2f} "
            f"| SL dist: ${sl_distance:.2f} | Leverage: {leverage}x"
        )
        return quantity

    def can_open_trade(self, open_positions: int) -> bool:
        """Check if another position can be opened."""
        if open_positions >= self.max_open:
            logger.info(f"Max open trades reached ({self.max_open}). Skipping.")
            return False
        return True

    def is_symbol_in_cooldown(self, symbol: str) -> tuple[bool, str]:
        """Check if a symbol is in cooldown after consecutive stop-losses."""
        now = time.time()
        expiry = self.symbol_cooldowns.get(symbol, 0)
        if now < expiry:
            remaining_mins = int((expiry - now) / 60)
            reason = f"Chop circuit breaker active ({remaining_mins}m remaining after consecutive losses)"
            return True, reason
        return False, ""

    def update_symbol_cooldown_from_trades(self, symbol: str, recent_trades: list):
        """
        Inspect recent trades for the symbol. If the last 2 closed trades were losses,
        trigger a cooldown to protect against sideways whipsaw.
        """
        if not recent_trades:
            return

        # Filter trades with realized PnL
        closed = [t for t in recent_trades if float(t.get("realizedPnl", 0)) != 0]
        if len(closed) >= 2:
            last_2 = closed[-2:]
            pnls = [float(t.get("realizedPnl", 0)) for t in last_2]
            if all(p < 0 for p in pnls):
                # Both trades were losses
                last_trade_time = float(last_2[-1].get("time", 0)) / 1000.0
                cooldown_end = last_trade_time + (self.cooldown_hours * 3600)
                now = time.time()
                if now < cooldown_end:
                    self.symbol_cooldowns[symbol] = cooldown_end
                    remaining_hrs = (cooldown_end - now) / 3600
                    logger.warning(
                        f"🛡️ [CHOP CIRCUIT BREAKER] {symbol} hit 2 consecutive losses "
                        f"(PnLs: ${pnls[0]:.2f}, ${pnls[1]:.2f}). Cooldown active for {remaining_hrs:.1f} hours."
                    )


