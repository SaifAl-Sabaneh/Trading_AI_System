import os
import sys
import json
import time
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database
from config.settings import TARGET_SYMBOLS

class ABTestSimulator:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()
        self.friction_pct = 0.0014 # 14 bps taker fee + slippage round trip

    def simulate_version_a(self, action: str, entry_price: float, forward_candles: List[Tuple]) -> float:
        """
        Version A: Fixed Baseline Execution (+2.5% Target / -1.2% Stop)
        """
        if not forward_candles or entry_price <= 0:
            return 0.0
            
        target_pct = 0.025
        stop_pct = 0.012
        
        if action in ["BUY", "CARRY_DELTA_NEUTRAL"]:
            target_price = entry_price * (1.0 + target_pct)
            stop_price   = entry_price * (1.0 - stop_pct)
        else: # SELL
            target_price = entry_price * (1.0 - target_pct)
            stop_price   = entry_price * (1.0 + stop_pct)
            
        for b in forward_candles[:24]:
            high, low, close = b[2], b[3], b[4]
            if action in ["BUY", "CARRY_DELTA_NEUTRAL"]:
                if high >= target_price:
                    return target_pct - self.friction_pct
                if low <= stop_price:
                    return -stop_pct - self.friction_pct
            else: # SELL
                if low <= target_price:
                    return target_pct - self.friction_pct
                if high >= stop_price:
                    return -stop_pct - self.friction_pct
                    
        final_close = forward_candles[min(24, len(forward_candles)-1)][4]
        if action in ["BUY", "CARRY_DELTA_NEUTRAL"]:
            raw_ret = (final_close - entry_price) / entry_price
        else:
            raw_ret = (entry_price - final_close) / entry_price
            
        return raw_ret - self.friction_pct

    def simulate_version_b(self, action: str, entry_price: float, forward_candles: List[Tuple]) -> float:
        """
        Version B: Dynamic Trade Management (TP1 at +1.0% with 50% partial exit + Breakeven move + Invalidation SL)
        """
        if not forward_candles or entry_price <= 0:
            return 0.0
            
        tp1_pct = 0.010        # +1.0% partial profit target
        stop_pct = 0.015       # -1.5% invalidation stop
        breakeven_pct = 0.0014 # Entry + 14 bps friction
        
        if action in ["BUY", "CARRY_DELTA_NEUTRAL"]:
            tp1_price  = entry_price * (1.0 + tp1_pct)
            stop_price = entry_price * (1.0 - stop_pct)
            be_price   = entry_price * (1.0 + breakeven_pct)
        else: # SELL
            tp1_price  = entry_price * (1.0 - tp1_pct)
            stop_price = entry_price * (1.0 + stop_pct)
            be_price   = entry_price * (1.0 - breakeven_pct)

        pos1 = 0.50
        pos2 = 0.50
        
        pos1_pnl = None
        pos2_pnl = None
        tp1_hit = False
        
        for b in forward_candles[:24]:
            high, low = b[2], b[3]
            
            if action in ["BUY", "CARRY_DELTA_NEUTRAL"]:
                if not tp1_hit and high >= tp1_price:
                    tp1_hit = True
                    pos1_pnl = tp1_pct - (self.friction_pct * 0.5)
                    stop_price = be_price
                    
                if low <= stop_price:
                    if not tp1_hit:
                        pos1_pnl = -stop_pct - (self.friction_pct * 0.5)
                        pos2_pnl = -stop_pct - (self.friction_pct * 0.5)
                        break
                    else:
                        pos2_pnl = breakeven_pct - (self.friction_pct * 0.5)
                        break
            else: # SELL
                if not tp1_hit and low <= tp1_price:
                    tp1_hit = True
                    pos1_pnl = tp1_pct - (self.friction_pct * 0.5)
                    stop_price = be_price
                    
                if high >= stop_price:
                    if not tp1_hit:
                        pos1_pnl = -stop_pct - (self.friction_pct * 0.5)
                        pos2_pnl = -stop_pct - (self.friction_pct * 0.5)
                        break
                    else:
                        pos2_pnl = breakeven_pct - (self.friction_pct * 0.5)
                        break
                        
        final_close = forward_candles[min(24, len(forward_candles)-1)][4]
        if action in ["BUY", "CARRY_DELTA_NEUTRAL"]:
            final_raw = (final_close - entry_price) / entry_price
        else:
            final_raw = (entry_price - final_close) / entry_price
            
        if pos1_pnl is None:
            pos1_pnl = final_raw - (self.friction_pct * 0.5)
        if pos2_pnl is None:
            pos2_pnl = final_raw - (self.friction_pct * 0.5)
            
        total_pnl = (pos1 * pos1_pnl) + (pos2 * pos2_pnl)
        return total_pnl

    def run_ab_test(self) -> pd.DataFrame:
        print("============================================================")
        print("  TRADE MANAGEMENT A/B TEST ENGINE -- COMPARATIVE MATRIX")
        print("  Version A: Fixed Baseline (+2.5% Target / -1.2% Stop)")
        print("  Version B: Dynamic Management (TP1 +1.0% / Breakeven Stop / Invalidation SL)")
        print("============================================================")
        
        with self.db.get_connection() as conn:
            df_mem = pd.read_sql("SELECT trade_id, symbol, timeframe, decision_timestamp, action, confidence, tier, entry_price, market_state_snapshot FROM trade_memory;", conn)
            
        if df_mem.empty:
            print("No trade memory decisions available for A/B testing.", flush=True)
            return pd.DataFrame()

        results_a = []
        results_b = []
        
        print(f"Running A/B evaluation across {len(df_mem)} historical decision memories...", flush=True)
        
        for idx, row in df_mem.iterrows():
            sym = row['symbol']
            tf = row['timeframe']
            ts = int(row['decision_timestamp'])
            action = row['action']
            entry_p = float(row['entry_price'])
            
            if action == 'NEUTRAL' or entry_p <= 0:
                continue
                
            forward = self.db.fetch_candles(sym, tf, start_ts=ts)
            if len(forward) < 25:
                continue
                
            pnl_a = self.simulate_version_a(action, entry_p, forward[1:])
            pnl_b = self.simulate_version_b(action, entry_p, forward[1:])
            
            try:
                agent_name = json.loads(row['market_state_snapshot']).get('agent_name', 'UnknownAgent')
            except:
                agent_name = 'UnknownAgent'
                
            results_a.append({"agent_name": agent_name, "symbol": sym, "pnl_pct": pnl_a})
            results_b.append({"agent_name": agent_name, "symbol": sym, "pnl_pct": pnl_b})
            
        df_a = pd.DataFrame(results_a)
        df_b = pd.DataFrame(results_b)
        
        metrics = []
        agents = df_a['agent_name'].unique()
        
        for agent in agents:
            sub_a = df_a[df_a['agent_name'] == agent]
            sub_b = df_b[df_b['agent_name'] == agent]
            
            if sub_a.empty or sub_b.empty:
                continue
                
            rets_a = sub_a['pnl_pct'].values
            rets_b = sub_b['pnl_pct'].values
            
            win_a = (rets_a > 0).mean()
            win_b = (rets_b > 0).mean()
            
            exp_a = rets_a.mean()
            exp_b = rets_b.mean()
            
            wins_a, losses_a = rets_a[rets_a > 0].sum(), abs(rets_a[rets_a < 0].sum())
            wins_b, losses_b = rets_b[rets_b > 0].sum(), abs(rets_b[rets_b < 0].sum())
            
            pf_a = (wins_a / losses_a) if losses_a > 0 else 0.0
            pf_b = (wins_b / losses_b) if losses_b > 0 else 0.0
            
            avg_win_a = rets_a[rets_a > 0].mean() if (rets_a > 0).any() else 0.0
            avg_win_b = rets_b[rets_b > 0].mean() if (rets_b > 0).any() else 0.0
            
            avg_loss_a = abs(rets_a[rets_a < 0].mean()) if (rets_a < 0).any() else 0.0
            avg_loss_b = abs(rets_b[rets_b < 0].mean()) if (rets_b < 0).any() else 0.0
            
            metrics.append({
                "Agent": agent,
                "n_trades": len(sub_a),
                "WinRate_A": f"{win_a*100:.1f}%",
                "WinRate_B": f"{win_b*100:.1f}%",
                "Expectancy_A": f"{exp_a*100:+.2f}%",
                "Expectancy_B": f"{exp_b*100:+.2f}%",
                "ProfitFactor_A": f"{pf_a:.2f}",
                "ProfitFactor_B": f"{pf_b:.2f}",
                "AvgWin_A/B": f"{avg_win_a*100:.2f}% / {avg_win_b*100:.2f}%",
                "AvgLoss_A/B": f"-{avg_loss_a*100:.2f}% / -{avg_loss_b*100:.2f}%",
                "Value_Created": "[YES (PF Improved)]" if pf_b > pf_a and exp_b > exp_a else "[NO]"
            })
            
        res_df = pd.DataFrame(metrics)
        return res_df

if __name__ == "__main__":
    tester = ABTestSimulator()
    df_res = tester.run_ab_test()
    print("\n" + "="*80)
    print("  SIDE-BY-SIDE A/B TESTING RESULTS MATRIX")
    print("="*80)
    print(df_res.to_string(index=False))
