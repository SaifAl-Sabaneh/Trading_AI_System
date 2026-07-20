import os
import sys
import json
import pandas as pd
import numpy as np
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database

class DistributionLogger:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()

    def compute_distribution_metrics(self) -> pd.DataFrame:
        with self.db.get_connection() as conn:
            df = pd.read_sql("""
            SELECT trade_id, symbol, action, realized_pnl_pct, market_state_snapshot 
            FROM trade_memory 
            WHERE evaluated_at IS NOT NULL;
            """, conn)
            
        if df.empty:
            return pd.DataFrame()
            
        def extract_agent(snapshot_json):
            try:
                return json.loads(snapshot_json).get("agent_name", "UnknownAgent")
            except:
                return "UnknownAgent"
                
        df['agent_name'] = df['market_state_snapshot'].apply(extract_agent)
        
        dist_metrics = []
        agents = df['agent_name'].unique()
        
        for agent in agents:
            sub = df[df['agent_name'] == agent].copy()
            if sub.empty:
                continue
                
            rets = sub['realized_pnl_pct'].values
            n_trades = len(rets)
            
            median_ret = float(np.median(rets))
            q25_ret = float(np.percentile(rets, 25))
            q75_ret = float(np.percentile(rets, 75))
            best_trade = float(np.max(rets))
            worst_trade = float(np.min(rets))
            
            # Max Consecutive Losses
            max_consec_losses = 0
            curr_consec = 0
            for r in rets:
                if r < 0:
                    curr_consec += 1
                    max_consec_losses = max(max_consec_losses, curr_consec)
                else:
                    curr_consec = 0
                    
            # Cumulative Drawdown Calculation
            cum_returns = np.cumsum(rets)
            peak = np.maximum.accumulate(cum_returns)
            drawdown = cum_returns - peak
            max_drawdown = float(np.min(drawdown)) if len(drawdown) > 0 else 0.0
            
            dist_metrics.append({
                "Agent": agent,
                "n_trades": n_trades,
                "Median_Return": f"{median_ret*100:+.2f}%",
                "Q25_Return": f"{q25_ret*100:+.2f}%",
                "Q75_Return": f"{q75_ret*100:+.2f}%",
                "Best_Trade": f"+{best_trade*100:.2f}%",
                "Worst_Trade": f"{worst_trade*100:.2f}%",
                "Max_Consec_Losses": max_consec_losses,
                "Max_Drawdown": f"{max_drawdown*100:.2f}%"
            })
            
        return pd.DataFrame(dist_metrics)

if __name__ == "__main__":
    logger = DistributionLogger()
    print("\n============================================================")
    print("  EXPANDED RETURN DISTRIBUTION REPORT")
    print("============================================================")
    print(logger.compute_distribution_metrics().to_string(index=False))
