import os
import sys
import pandas as pd
import numpy as np
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database

class CarryEvaluator:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()

    def evaluate_carry_performance(self, symbol: str, days_held: int = 14) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            df_funding = pd.read_sql("SELECT timestamp, funding_rate, mark_price FROM funding_rates WHERE symbol = ? ORDER BY timestamp ASC;", conn, params=[symbol])
            
        if df_funding.empty or len(df_funding) < 10:
            return {"symbol": symbol, "status": "INSUFFICIENT_DATA"}

        # Calculate accrued funding over holding period
        funding_sum = df_funding['funding_rate'].sum()
        avg_funding_8h = df_funding['funding_rate'].mean()
        annualized_funding_apr = avg_funding_8h * 3 * 365
        
        # Friction assumptions (round trip entry/exit spot + perp)
        total_friction_pct = 0.0014 # 14 bps total friction
        
        net_annualized_yield = annualized_funding_apr - total_friction_pct
        
        return {
            "symbol": symbol,
            "total_funding_events": len(df_funding),
            "sum_funding_collected_pct": funding_sum * 100.0,
            "avg_funding_8h_pct": avg_funding_8h * 100.0,
            "gross_funding_apr": annualized_funding_apr * 100.0,
            "friction_deducted_pct": total_friction_pct * 100.0,
            "net_carry_apr": net_annualized_yield * 100.0,
            "status": "VIABLE_STRUCTURAL_CARRY" if net_annualized_yield > 0.05 else "LOW_YIELD"
        }

if __name__ == "__main__":
    evaluator = CarryEvaluator()
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        print(evaluator.evaluate_carry_performance(sym))
