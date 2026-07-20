import os
import sys
import json
import time
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database_history import HistoryDatabase
from features.technical_features import TechnicalFeatureExtractor
from features.derivative_features import DerivativeFeatureExtractor
from strategies.research.funding_reversion import FundingReversionAgent
from simulation.ab_test_simulator import ABTestSimulator

class FundingReversionCampaignRunner:
    def __init__(self, db: HistoryDatabase = None):
        self.db = db if db else HistoryDatabase()
        self.agent = FundingReversionAgent()
        self.ab_simulator = ABTestSimulator()

    def run_campaign(self, symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT"], timeframe="1h") -> pd.DataFrame:
        print("============================================================")
        print("  RESEARCH CAMPAIGN #1: FUNDING RATE EXTREME REVERSION (HYP-FUND-REV-V1)")
        print("  Target Dataset: market_history.db (2020-11 to 2024-07 Gold Standard)")
        print(f"  Target Assets ({len(symbols)}): {', '.join(symbols)}")
        print("  Pre-Registered Entry: Funding Percentile >= 90%, OI Z-Score >= 1.0")
        print("============================================================")
        
        start_time = time.time()
        campaign_results = []
        
        with self.db.get_connection() as conn:
            df_funding_all = pd.read_sql("SELECT symbol, timestamp, funding_rate, mark_price FROM funding_rates_history;", conn)
            df_oi_all = pd.read_sql("SELECT symbol, timestamp, open_interest, open_interest_usd FROM open_interest_history;", conn)

        for symbol in symbols:
            print(f"\n>>> Running Campaign Scan for {symbol} ({timeframe})...", flush=True)
            candles = self.db.fetch_candles(symbol, timeframe)
            if not candles or len(candles) < 100:
                print(f"  Skip {symbol}: insufficient candles.", flush=True)
                continue
                
            cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df_full = pd.DataFrame([c[:6] for c in candles], columns=cols)
            
            df_funding = df_funding_all[df_funding_all['symbol'] == symbol]
            df_oi = df_oi_all[df_oi_all['symbol'] == symbol]
            
            df_full = TechnicalFeatureExtractor.compute_features(df_full)
            df_full = DerivativeFeatureExtractor.compute_features(df_full, df_funding, df_oi)
            
            # Step forward bar-by-bar
            signals_count = 0
            for i in range(50, len(df_full) - 25):
                df_window = df_full.iloc[:i+1]
                latest_bar = df_window.iloc[-1]
                entry_p = float(latest_bar['close'])
                
                dec = self.agent.evaluate(symbol, timeframe, df_window)
                act = dec["action"]
                if act == "NEUTRAL":
                    continue
                    
                forward_bars = candles[i+1 : i+26]
                if len(forward_bars) < 25:
                    continue
                    
                signals_count += 1
                # Evaluate Out-Of-Sample outcome (Version B dynamic exits)
                pnl_oos = self.ab_simulator.simulate_version_b(act, entry_p, forward_bars)
                
                campaign_results.append({
                    "symbol": symbol,
                    "action": act,
                    "confidence": dec["confidence"],
                    "entry_price": entry_p,
                    "pnl_pct": pnl_oos
                })
                
            print(f"  {symbol}: generated {signals_count} signals.", flush=True)

        elapsed = time.time() - start_time
        print(f"\n============================================================")
        print(f"  CAMPAIGN SCAN COMPLETE: Recorded {len(campaign_results)} decisions in {elapsed:.2f}s.")
        print("============================================================")
        
        df_res = pd.DataFrame(campaign_results)
        if df_res.empty:
            print("No signals triggered under strict pre-registered parameters.")
            return pd.DataFrame([{
                "Hypothesis_ID": "HYP-FUND-REV-V1",
                "OOS_Sample_Count": 0,
                "OOS_Win_Rate": "0.0%",
                "OOS_Expectancy": "0.00%",
                "OOS_Profit_Factor": "0.00",
                "Governance_Verdict": "[UNTESTED] (Required market conditions absent from dataset)"
            }])
            
        rets = df_res['pnl_pct'].values
        n_trades = len(rets)
        win_rate = float((rets > 0).mean())
        exp_pnl = float(rets.mean())
        wins, losses = rets[rets > 0].sum(), abs(rets[rets < 0].sum())
        pf = float(wins / losses) if losses > 0 else 0.0
        
        # Governance Audit Decision (5-Category Rules)
        if n_trades < 100:
            verdict = "[INSUFFICIENT EVIDENCE] (Sample size n < 100 OOS threshold)"
        elif pf >= 1.20 and exp_pnl > 0.0010:
            verdict = "[PRODUCTION CANDIDATE] (Passed Gates 0-7)"
        else:
            verdict = "[FALSIFIED] (Failed OOS Profit Factor PF < 1.20)"
            
        summary = pd.DataFrame([{
            "Hypothesis_ID": "HYP-FUND-REV-V1",
            "OOS_Sample_Count": n_trades,
            "OOS_Win_Rate": f"{win_rate*100:.1f}%",
            "OOS_Expectancy": f"{exp_pnl*100:+.2f}%",
            "OOS_Profit_Factor": f"{pf:.2f}",
            "Governance_Verdict": verdict
        }])
        
        # Update manifest YAML
        manifest_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "governance", "evidence_manifests", "HYP-FUND-REV-V1.yaml")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r") as f:
                content = f.read()
            content = content.replace('oos_sample_size: 41', f'oos_sample_size: {n_trades}')
            content = content.replace('oos_profit_factor: 0.13', f'oos_profit_factor: {pf:.2f}')
            content = content.replace('oos_expectancy: "0.00%"', f'oos_expectancy: "{exp_pnl*100:+.2f}%"')
            with open(manifest_path, "w") as f:
                f.write(content)
                
        return summary

if __name__ == "__main__":
    runner = FundingReversionCampaignRunner()
    df_verdict = runner.run_campaign()
    print("\n" + "="*80)
    print("  RESEARCH CAMPAIGN #1: AUDIT VERDICT TABLE")
    print("="*80)
    print(df_verdict.to_string(index=False))
