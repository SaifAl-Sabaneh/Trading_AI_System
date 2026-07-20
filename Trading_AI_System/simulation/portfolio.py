import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import ACCOUNT_VALIDATION_BALANCE_USD

class Portfolio:
    def __init__(self, initial_balance: float = ACCOUNT_VALIDATION_BALANCE_USD):
        self.initial_balance = initial_balance
        self.cash_balance = initial_balance
        self.active_positions = {}
        self.realized_pnl_usd = 0.0

    def update_balance(self, pnl_usd: float):
        self.realized_pnl_usd += pnl_usd
        self.cash_balance += pnl_usd

    def get_summary(self) -> dict:
        total_value = self.cash_balance + sum(p.get("usd_value", 0.0) for p in self.active_positions.values())
        roi_pct = ((total_value - self.initial_balance) / self.initial_balance) * 100.0
        return {
            "initial_balance_usd": self.initial_balance,
            "cash_balance_usd": self.cash_balance,
            "total_portfolio_value_usd": total_value,
            "realized_pnl_usd": self.realized_pnl_usd,
            "roi_pct": roi_pct,
            "active_positions_count": len(self.active_positions)
        }

if __name__ == "__main__":
    port = Portfolio(200.0)
    print("Portfolio Summary:", port.get_summary())
