import json
import time
import os
import sys
import pandas as pd
import numpy as np
from typing import Dict, Any, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database

class Evaluator:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()

    @staticmethod
    def get_confidence_bucket(conf: float) -> str:
        if conf >= 0.80:
            return "80-90%"
        elif conf >= 0.70:
            return "70-80%"
        elif conf >= 0.60:
            return "60-70%"
        else:
            return "50-60%"

    def evaluate_all_unmatured_memories(self) -> int:
        """
        Evaluates all trade memories against forward candle prices (1h, 4h, 24h MFE & MAE).
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT trade_id, symbol, timeframe, decision_timestamp, action, entry_price 
            FROM trade_memory WHERE evaluated_at IS NULL;
            """)
            unevaluated = cursor.fetchall()
            
            evaluated_count = 0
            now_ts = int(time.time() * 1000)
            
            for trade_id, symbol, tf, dec_ts, action, entry_price in unevaluated:
                if not entry_price or entry_price <= 0:
                    continue
                    
                # Fetch forward 24 candles
                forward_candles = self.db.fetch_candles(symbol, tf, start_ts=dec_ts)
                if len(forward_candles) < 25:
                    continue  # Need at least 24 forward bars
                    
                # 1h forward (index 1)
                bars_1h = forward_candles[1:2]
                # 4h forward (index 1 to 4)
                bars_4h = forward_candles[1:5]
                # 24h forward (index 1 to 25)
                bars_24h = forward_candles[1:25]
                
                # Compute MFE and MAE for 1h, 4h, 24h
                def calc_excursion(bars, act, entry):
                    if not bars:
                        return 0.0, 0.0, 0.0
                    highs = [b[2] for b in bars]
                    lows = [b[3] for b in bars]
                    close = bars[-1][4]
                    if act in ["BUY", "CARRY_DELTA_NEUTRAL"]:
                        ret = (close - entry) / entry
                        mfe = (max(highs) - entry) / entry
                        mae = (min(lows) - entry) / entry
                    else:
                        ret = (entry - close) / entry
                        mfe = (entry - min(lows)) / entry
                        mae = (entry - max(highs)) / entry
                    return ret, mfe, mae
                    
                ret_1h, mfe_1h, mae_1h = calc_excursion(bars_1h, action, entry_price)
                ret_4h, mfe_4h, mae_4h = calc_excursion(bars_4h, action, entry_price)
                ret_24h, mfe_24h, mae_24h = calc_excursion(bars_24h, action, entry_price)
                
                # Decision Quality Score (0 to 100) based on 24h return, MFE, and MAE
                score = 50.0 + (ret_24h * 1000.0) + (mfe_24h * 500.0) + (mae_24h * 500.0)
                score = max(0.0, min(100.0, score))
                
                cursor.execute("""
                UPDATE trade_memory 
                SET exit_price = ?, realized_pnl_pct = ?, 
                    mfe_1h_pct = ?, mae_1h_pct = ?,
                    mfe_4h_pct = ?, mae_4h_pct = ?,
                    mfe_24h_pct = ?, mae_24h_pct = ?,
                    decision_quality_score = ?, evaluated_at = ?
                WHERE trade_id = ?;
                """, (bars_24h[-1][4], ret_24h, mfe_1h, mae_1h, mfe_4h, mae_4h, mfe_24h, mae_24h, score, now_ts, trade_id))
                
                evaluated_count += 1
                
            conn.commit()
            return evaluated_count

    def generate_strategy_calibration_report(self) -> pd.DataFrame:
        """
        Aggregates evaluated trade memories into strategy_statistics table and returns calibration report.
        """
        self.evaluate_all_unmatured_memories()
        
        with self.db.get_connection() as conn:
            df = pd.read_sql("SELECT * FROM trade_memory WHERE evaluated_at IS NOT NULL;", conn)
            
        if df.empty:
            print("No evaluated trade memories found yet.", flush=True)
            return pd.DataFrame()
            
        df['confidence_bucket'] = df['confidence'].apply(self.get_confidence_bucket)
        
        # Parse market state
        def extract_regime(snapshot_json):
            try:
                data = json.loads(snapshot_json)
                return data.get("regime", "NORMAL")
            except:
                return "NORMAL"
                
        df['market_state'] = df['market_state_snapshot'].apply(extract_regime)
        def extract_agent(snapshot_json):
            try:
                data = json.loads(snapshot_json)
                return data.get("agent_name", "UnknownAgent")
            except:
                return "UnknownAgent"
        df['strategy_name'] = df['market_state_snapshot'].apply(extract_agent)

        stats_rows = []
        now_ts = int(time.time() * 1000)
        
        grouped = df.groupby(['strategy_name', 'symbol', 'timeframe', 'market_state', 'confidence_bucket'])
        
        for (strat, sym, tf, mkt, bucket), group in grouped:
            n_dec = len(group)
            executed = len(group[group['action'] != 'NEUTRAL'])
            
            rets = group['realized_pnl_pct'].values
            win_rate = float((rets > 0).mean()) if n_dec > 0 else 0.0
            mean_ret = float(rets.mean()) if n_dec > 0 else 0.0
            total_ret = float(rets.sum()) if n_dec > 0 else 0.0
            
            wins = rets[rets > 0].sum()
            losses = abs(rets[rets < 0].sum())
            profit_factor = float(wins / losses) if losses > 0 else (10.0 if wins > 0 else 0.0)
            
            avg_mfe = float(group['mfe_24h_pct'].mean()) if 'mfe_24h_pct' in group else 0.0
            avg_mae = float(group['mae_24h_pct'].mean()) if 'mae_24h_pct' in group else 0.0
            
            # Target confidence midpoint
            conf_midpoint = 0.65 if bucket == "60-70%" else (0.75 if bucket == "70-80%" else 0.85)
            calibrated_acc = win_rate - conf_midpoint
            
            stats_rows.append((
                strat, sym, tf, mkt, bucket, n_dec, executed, win_rate, mean_ret, total_ret,
                profit_factor, avg_mfe, avg_mae, calibrated_acc, now_ts
            ))
            
        self.db.insert_strategy_statistics(stats_rows)
        
        summary_cols = ['strategy_name', 'symbol', 'timeframe', 'confidence_bucket', 
                        'n_decisions', 'win_rate', 'mean_return_pct', 'profit_factor', 
                        'avg_mfe_pct', 'avg_mae_pct', 'calibrated_accuracy']
        summary_df = pd.DataFrame(stats_rows, columns=[
            'strategy_name', 'symbol', 'timeframe', 'market_state', 'confidence_bucket', 
            'n_decisions', 'n_executed', 'win_rate', 'mean_return_pct', 'total_return_pct', 
            'profit_factor', 'avg_mfe_pct', 'avg_mae_pct', 'calibrated_accuracy', 'last_updated'
        ])[summary_cols]
        
        return summary_df

if __name__ == "__main__":
    evaluator = Evaluator()
    report = evaluator.generate_strategy_calibration_report()
    print("Calibration Summary Report:")
    print(report)
