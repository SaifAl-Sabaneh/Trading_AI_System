import os
import sys
import time
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import TARGET_SYMBOLS
from database.database import Database
from features.technical_features import TechnicalFeatureExtractor
from features.derivative_features import DerivativeFeatureExtractor
from features.market_state import MarketStateClassifier
from strategies.production.carry import CarryAgent
from strategies.research.momentum import MomentumAgent
from strategies.research.mean_reversion import MeanReversionAgent
from strategies.research.liquidation import LiquidationAgent
from simulation.ab_test_simulator import ABTestSimulator

class WalkForwardEvaluator:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()
        self.ab_simulator = ABTestSimulator(db=self.db)
        self.agents = [
            CarryAgent(),
            MomentumAgent(),
            MeanReversionAgent(),
            LiquidationAgent()
        ]

    def run_walk_forward_evaluation(self, symbols=TARGET_SYMBOLS, timeframe="1h", train_bars=300, test_bars=150) -> pd.DataFrame:
        print("============================================================")
        print("  WALK-FORWARD EVALUATION ENGINE -- FROZEN OOS PARAMETERS")
        print(f"  Target Assets ({len(symbols)}): {', '.join(symbols)}")
        print(f"  Train Window (IS): {train_bars} bars | Test Window (OOS): {test_bars} bars")
        print("============================================================")
        
        start_time = time.time()
        oos_results = []
        
        with self.db.get_connection() as conn:
            df_funding_all = pd.read_sql("SELECT symbol, timestamp, funding_rate, mark_price FROM funding_rates;", conn)
            df_oi_all = pd.read_sql("SELECT symbol, timestamp, open_interest, open_interest_usd FROM open_interest;", conn)

        for symbol in symbols:
            print(f"\n>>> Running Walk-Forward Rolls for {symbol} ({timeframe})...", flush=True)
            candles = self.db.fetch_candles(symbol, timeframe)
            if not candles or len(candles) < (train_bars + test_bars + 25):
                print(f"  Skip {symbol}: insufficient candles.", flush=True)
                continue
                
            cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df_full = pd.DataFrame([c[:6] for c in candles], columns=cols)
            
            df_funding = df_funding_all[df_funding_all['symbol'] == symbol]
            df_oi = df_oi_all[df_oi_all['symbol'] == symbol]
            
            df_full = TechnicalFeatureExtractor.compute_features(df_full)
            df_full = DerivativeFeatureExtractor.compute_features(df_full, df_funding, df_oi)
            
            # Rolling window loop: Train on [start..train_end], Test on [train_end..test_end]
            start_idx = 50
            roll_step = test_bars
            
            window_count = 0
            
            while (start_idx + train_bars + test_bars) < len(df_full) - 25:
                train_df = df_full.iloc[start_idx : start_idx + train_bars]
                test_df  = df_full.iloc[start_idx + train_bars : start_idx + train_bars + test_bars]
                
                # 1. Calibrate In-Sample exit heuristic on train_df
                # Simple median MFE on train_df
                mfe_train = (train_df['high'] - train_df['close']) / train_df['close']
                frozen_tp1_target = max(0.008, float(mfe_train.median()) * 0.60)
                
                window_count += 1
                
                # 2. Evaluate FROZEN OOS test window
                for idx in range(len(test_df)):
                    curr_bar_idx = start_idx + train_bars + idx
                    window_sub = df_full.iloc[:curr_bar_idx + 1]
                    latest_bar = window_sub.iloc[-1]
                    dec_ts = int(latest_bar['timestamp'])
                    entry_p = float(latest_bar['close'])
                    
                    forward_bars = candles[curr_bar_idx + 1 : curr_bar_idx + 26]
                    if len(forward_bars) < 25:
                        continue
                        
                    for agent in self.agents:
                        dec = agent.evaluate(symbol, timeframe, window_sub)
                        act = dec["action"]
                        if act == "NEUTRAL":
                            continue
                            
                        # Evaluate using frozen parameters (Version B)
                        pnl_oos = self.ab_simulator.simulate_version_b(act, entry_p, forward_bars)
                        
                        oos_results.append({
                            "window": window_count,
                            "symbol": symbol,
                            "agent_name": agent.name,
                            "tier": getattr(agent, "tier", "RESEARCH"),
                            "frozen_tp1": frozen_tp1_target,
                            "pnl_pct": pnl_oos
                        })
                        
                start_idx += roll_step

        elapsed = time.time() - start_time
        print(f"\n============================================================")
        print(f"  WALK-FORWARD EVALUATION COMPLETE: {len(oos_results)} OOS trades in {elapsed:.2f}s.")
        print("============================================================")
        
        df_oos = pd.DataFrame(oos_results)
        if df_oos.empty:
            return pd.DataFrame()
            
        summary_rows = []
        for agent in df_oos['agent_name'].unique():
            sub = df_oos[df_oos['agent_name'] == agent]
            rets = sub['pnl_pct'].values
            n_trades = len(rets)
            
            win_rate = float((rets > 0).mean())
            exp_pnl = float(rets.mean())
            wins, losses = rets[rets > 0].sum(), abs(rets[rets < 0].sum())
            pf = float(wins / losses) if losses > 0 else 0.0
            
            # Status classification rules
            if agent == "LiquidationAgent":
                status = "PROMISING - UNVERIFIED (n < 100)" if n_trades < 100 else ("PROMOTED" if pf > 1.2 and exp_pnl > 0 else "DEMOTED")
            elif agent == "MomentumAgent":
                status = "UNRECOVERED (PF < 1.0)" if pf < 1.0 else ("PROMOTED" if pf > 1.2 else "MARGINAL")
            else:
                status = "PROMOTED (PF > 1.2)" if pf > 1.2 and exp_pnl > 0 else "RESEARCH SANDBOX"
                
            summary_rows.append({
                "Agent": agent,
                "OOS_Trades_Count": n_trades,
                "OOS_Win_Rate": f"{win_rate*100:.1f}%",
                "OOS_Expectancy": f"{exp_pnl*100:+.2f}%",
                "OOS_Profit_Factor": f"{pf:.2f}",
                "Classification_Status": status
            })
            
        return pd.DataFrame(summary_rows)

if __name__ == "__main__":
    wfe = WalkForwardEvaluator()
    df_summary = wfe.run_walk_forward_evaluation(train_bars=300, test_bars=150)
    print("\n" + "="*80)
    print("  WALK-FORWARD OOS STRESS TEST REPORT")
    print("="*80)
    print(df_summary.to_string(index=False))
