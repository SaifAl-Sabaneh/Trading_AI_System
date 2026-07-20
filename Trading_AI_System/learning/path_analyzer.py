import os
import sys
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database

class PathAnalyzer:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()

    def analyze_trade_paths(self) -> pd.DataFrame:
        with self.db.get_connection() as conn:
            df = pd.read_sql("""
            SELECT trade_id, symbol, timeframe, action, entry_price, mfe_24h_pct, mae_24h_pct, realized_pnl_pct, market_state_snapshot 
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
        
        path_metrics = []
        agents = df['agent_name'].unique()
        
        tp1_target = 0.010 # +1.0% TP1
        stop_target = 0.015 # -1.5% SL
        
        for agent in agents:
            sub = df[df['agent_name'] == agent]
            if sub.empty:
                continue
                
            n_trades = len(sub)
            
            # 1. TP1 First Hit Rate
            tp1_hits = (sub['mfe_24h_pct'] >= tp1_target).sum()
            tp1_hit_rate = tp1_hits / n_trades
            
            # 2. Trade Saver Rate: Reached TP1, but max drawdown went beyond entry level (saved by breakeven)
            saved_trades = ((sub['mfe_24h_pct'] >= tp1_target) & (sub['mae_24h_pct'] <= -tp1_target)).sum()
            saver_rate = saved_trades / n_trades
            
            # 3. Truncation Rate: Reached TP1, but MFE went beyond +3.0% (clipped potential big winner)
            truncated_trades = ((sub['mfe_24h_pct'] >= tp1_target) & (sub['mfe_24h_pct'] >= 0.030)).sum()
            truncation_rate = truncated_trades / n_trades
            
            # 4. Average MFE vs MAE
            avg_mfe = sub['mfe_24h_pct'].mean()
            avg_mae = sub['mae_24h_pct'].mean()
            
            path_metrics.append({
                "Agent": agent,
                "n_trades": n_trades,
                "TP1_Hit_Rate": f"{tp1_hit_rate*100:.1f}%",
                "Trade_Saver_Rate": f"{saver_rate*100:.1f}%",
                "Truncation_Rate": f"{truncation_rate*100:.1f}%",
                "Avg_MFE": f"+{avg_mfe*100:.2f}%",
                "Avg_MAE": f"{avg_mae*100:.2f}%",
                "Trajectory_Diagnosis": "Early MFE Edge + Reversal Risk" if tp1_hit_rate > 0.50 else "Weak Initial Direction"
            })
            
        return pd.DataFrame(path_metrics)

if __name__ == "__main__":
    analyzer = PathAnalyzer()
    report = analyzer.analyze_trade_paths()
    print("\n============================================================")
    print("  TRADE PATH & TRAJECTORY ANALYSIS REPORT")
    print("============================================================")
    print(report.to_string(index=False))
