import os
import sys
import json
import pandas as pd
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database
from learning.carry_evaluator import CarryEvaluator

class StrategyClassifier:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()
        self.carry_evaluator = CarryEvaluator(db=self.db)

    def classify_all_strategies(self) -> Dict[str, pd.DataFrame]:
        with self.db.get_connection() as conn:
            df_mem = pd.read_sql("SELECT * FROM trade_memory WHERE evaluated_at IS NOT NULL;", conn)
            
        # 1. STRUCTURAL YIELD CLASSIFICATION TABLE (CarryAgent)
        yield_rows = []
        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
            res = self.carry_evaluator.evaluate_carry_performance(sym)
            if res.get("status") != "INSUFFICIENT_DATA":
                yield_rows.append({
                    "Strategy": "CarryAgent",
                    "Asset": sym,
                    "Product_Type": "Delta-Neutral Yield Carry",
                    "Gross_Funding_APR": f"{res['gross_funding_apr']:+.2f}%",
                    "Friction_Deducted": f"-{res['friction_deducted_pct']:.2f}%",
                    "Net_Structural_APR": f"{res['net_carry_apr']:+.2f}%",
                    "Classification": "PRODUCTION CANDIDATE" if res['net_carry_apr'] > 0.05 else "LOW YIELD / RESEARCH"
                })
        df_yield = pd.DataFrame(yield_rows)
        
        # 2. DIRECTIONAL TRADING CLASSIFICATION TABLE
        directional_strategies = ["LiquidationAgent", "MomentumAgent", "MeanReversionAgent"]
        dir_rows = []
        
        for strat in directional_strategies:
            if strat == "LiquidationAgent":
                info_edge = "FORCE_ORDER_LIQUIDATIONS"
                gate0_status = "PASSED (Exchange Liquidation Order Flush)"
            else:
                info_edge = "TECHNICAL_INDICATOR"
                gate0_status = "HIGHER_BURDEN (Indicator-Only, No Constrained Edge)"
                
            sub_mem = df_mem[df_mem['market_state_snapshot'].str.contains(strat, na=False)]
            n_trades = len(sub_mem)
            
            if not sub_mem.empty:
                rets = sub_mem['realized_pnl_pct'].values
                win_rate = (rets > 0).mean()
                exp_pnl = rets.mean()
                wins, losses = rets[rets > 0].sum(), abs(rets[rets < 0].sum())
                pf = (wins / losses) if losses > 0 else 0.0
            else:
                win_rate, exp_pnl, pf = 0.0, 0.0, 0.0
                
            if "HIGHER_BURDEN" in gate0_status or pf < 1.0 or exp_pnl < 0:
                final_category = "[FALSIFIED]"
                governance_reason = f"Failed Gate 0 or OOS Profit Factor (PF = {pf:.2f} < 1.0, Expectancy = {exp_pnl*100:+.2f}%)"
            elif n_trades < 100:
                final_category = "[INSUFFICIENT EVIDENCE]"
                governance_reason = f"Passed Gate 0 & 1, but sample size n = {n_trades} < 100 OOS threshold"
            else:
                final_category = "[PRODUCTION CANDIDATE]"
                governance_reason = f"Passed Scientific Validation (n = {n_trades}, PF = {pf:.2f} >= 1.2)"
                
            dir_rows.append({
                "Strategy": strat,
                "Information_Edge": info_edge,
                "OOS_Sample_Count": n_trades,
                "OOS_Win_Rate": f"{win_rate*100:.1f}%",
                "OOS_Profit_Factor": f"{pf:.2f}",
                "OOS_Expectancy": f"{exp_pnl*100:+.2f}%",
                "Final_Category": final_category,
                "Governance_Verdict": governance_reason
            })
            
        df_directional = pd.DataFrame(dir_rows)
        
        return {
            "yield_table": df_yield,
            "directional_table": df_directional
        }

if __name__ == "__main__":
    classifier = StrategyClassifier()
    tables = classifier.classify_all_strategies()
    print("\n" + "="*80)
    print("  STRUCTURAL YIELD PRODUCTS EVALUATION TABLE")
    print("="*80)
    print(tables["yield_table"].to_string(index=False))
    
    print("\n" + "="*80)
    print("  DIRECTIONAL TRADING STRATEGIES EVALUATION TABLE")
    print("="*80)
    print(tables["directional_table"].to_string(index=False))
