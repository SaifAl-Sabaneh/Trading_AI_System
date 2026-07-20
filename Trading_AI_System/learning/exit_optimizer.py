import os
import sys
import pandas as pd
import numpy as np
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database

class ExitOptimizer:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()

    def derive_optimal_exit_rules(self, strategy_name: str, symbol: str) -> Dict[str, Any]:
        """
        Analyzes historical MFE/MAE distributions for a specific strategy and symbol
        to calculate optimal TP1, Breakeven trigger, and Trailing Stop parameters.
        """
        with self.db.get_connection() as conn:
            df = pd.read_sql("""
            SELECT mfe_24h_pct, mae_24h_pct, realized_pnl_pct 
            FROM trade_memory 
            WHERE evaluated_at IS NOT NULL 
              AND json_extract(market_state_snapshot, '$.agent_name') = ?
              AND symbol = ?;
            """, conn, params=[strategy_name, symbol])
            
        if df.empty or len(df) < 10:
            # Default fallback exit parameters
            return {
                "strategy_name": strategy_name,
                "symbol": symbol,
                "tp1_target_pct": 0.012,     # 1.2% partial profit target
                "tp1_ratio": 0.50,          # Exit 50% at TP1
                "breakeven_trigger_pct": 0.012,
                "trailing_atr_mult": 1.0,
                "invalidation_stop_pct": 0.015
            }
            
        median_mfe = float(df['mfe_24h_pct'].median())
        p75_mae = float(df['mae_24h_pct'].quantile(0.75)) # 75th percentile adverse drawdown
        
        # Optimal TP1 target is ~60% of median MFE
        tp1_target = max(0.008, median_mfe * 0.60)
        # Invalidation stop is set near 75th percentile MAE
        invalidation_stop = max(0.010, abs(p75_mae) * 1.1)
        
        return {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "sample_size": len(df),
            "median_mfe_pct": median_mfe,
            "p75_mae_pct": p75_mae,
            "tp1_target_pct": tp1_target,
            "tp1_ratio": 0.50,
            "breakeven_trigger_pct": tp1_target,
            "trailing_atr_mult": 1.0,
            "invalidation_stop_pct": invalidation_stop
        }

if __name__ == "__main__":
    opt = ExitOptimizer()
    print("Derived Exit Rules for MomentumAgent AVAXUSDT:")
    print(opt.derive_optimal_exit_rules("MomentumAgent", "AVAXUSDT"))
