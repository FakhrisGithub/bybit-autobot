"""
risk_manager.py — Circuit breaker untuk full-auto trading.
Tanpa modul ini, bot full-auto bisa terus entry walau lagi kalah beruntun
atau drawdown sudah parah. Modul ini yang "menahan" bot.
"""

import time
import csv
import os
from datetime import datetime, timezone

import config


class RiskManager:
    def __init__(self):
        self.day_start_balance = None
        self.day_start_ts = self._today_key()
        self.consecutive_losses = 0
        self.paused_until = 0
        self.open_positions = {}  # symbol -> {entry_time, side, ...}

        if not os.path.exists(config.LOG_FILE):
            with open(config.LOG_FILE, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "symbol", "side", "entry_price", "exit_price",
                    "sl", "tp1", "score", "grade", "pnl_usdt", "exit_reason"
                ])

    def _today_key(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _maybe_reset_day(self, current_balance: float):
        today = self._today_key()
        if today != self.day_start_ts:
            self.day_start_ts = today
            self.day_start_balance = current_balance
            print(f"[risk] New day. Reset day_start_balance = {current_balance}")

    def init_day(self, current_balance: float):
        if self.day_start_balance is None:
            self.day_start_balance = current_balance
            print(f"[risk] Day start balance set to {current_balance}")

    def is_paused(self) -> tuple[bool, str]:
        if time.time() < self.paused_until:
            remaining_min = round((self.paused_until - time.time()) / 60, 1)
            return True, f"Paused for {remaining_min} more minutes (max consecutive loss hit)"
        return False, ""

    def can_open_new_position(self, current_balance: float) -> tuple[bool, str]:
        self._maybe_reset_day(current_balance)
        self.init_day(current_balance)

        paused, reason = self.is_paused()
        if paused:
            return False, reason

        if len(self.open_positions) >= config.MAX_CONCURRENT_POSITIONS:
            return False, f"Max concurrent positions reached ({config.MAX_CONCURRENT_POSITIONS})"

        if self.day_start_balance and self.day_start_balance > 0:
            daily_pnl_pct = (current_balance - self.day_start_balance) / self.day_start_balance * 100
            if daily_pnl_pct <= -config.DAILY_LOSS_LIMIT_PCT:
                return False, f"Daily loss limit hit ({daily_pnl_pct:.2f}% <= -{config.DAILY_LOSS_LIMIT_PCT}%)"

        return True, "OK"

    def register_open(self, symbol: str, side: str, entry_price: float, sl: float, tp1: float):
        self.open_positions[symbol] = {
            "side": side, "entry_price": entry_price, "sl": sl, "tp1": tp1,
            "opened_at": time.time(),
        }

    def register_close(self, symbol: str, exit_price: float, pnl_usdt: float, exit_reason: str,
                        score: float = None, grade: str = None):
        pos = self.open_positions.pop(symbol, {})

        if pnl_usdt < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            self.paused_until = time.time() + config.PAUSE_AFTER_MAX_LOSS_MIN * 60
            print(f"[risk] {self.consecutive_losses} consecutive losses. "
                  f"Pausing new entries for {config.PAUSE_AFTER_MAX_LOSS_MIN} minutes.")

        with open(config.LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                symbol, pos.get("side", "?"), pos.get("entry_price", "?"), exit_price,
                pos.get("sl", "?"), pos.get("tp1", "?"), score, grade, round(pnl_usdt, 4), exit_reason,
            ])

    def positions_needing_time_exit(self) -> list:
        """Return list simbol yang sudah lewat TIME_EXIT_MINUTES dan belum closed."""
        now = time.time()
        limit_sec = config.TIME_EXIT_MINUTES * 60
        return [
            sym for sym, pos in self.open_positions.items()
            if now - pos["opened_at"] >= limit_sec
        ]

    def is_symbol_open(self, symbol: str) -> bool:
        return symbol in self.open_positions
