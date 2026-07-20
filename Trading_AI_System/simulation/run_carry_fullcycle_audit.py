import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database_history import HistoryDatabase

class FullCycleCarryAuditor:
    def __init__(self, db: HistoryDatabase = None):
        self.db = db if db else HistoryDatabase()
        self.entry_friction_pct = 0.0014 # 14 bps taker/maker round trip entry/exit

    def run_audit(self, symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"]) -> pd.DataFrame:
        print("============================================================")
        print("  FULL-CYCLE DELTA-NEUTRAL CARRY AUDIT (HYP-CARRY-V1)")
        print("  Target Dataset: market_history.db (Nov 2020 - Jul 2024, 3.5 Years)")
        print(f"  Symbols ({len(symbols)}): {', '.join(symbols)}")
        print("============================================================")
        
        audit_results = []
        
        with self.db.get_connection() as conn:
            for symbol in symbols:
                df_f = pd.read_sql(
                    "SELECT timestamp, funding_rate FROM funding_rates_history WHERE symbol = ? ORDER BY timestamp ASC;",
                    conn, params=[symbol]
                )
                if df_f.empty:
                    print(f"  Skip {symbol}: no funding data.")
                    continue
                    
                n_settlements = len(df_f)
                start_ts = df_f['timestamp'].iloc[0]
                end_ts = df_f['timestamp'].iloc[-1]
                years = (end_ts - start_ts) / (1000 * 86400 * 365.25)
                
                # Gross accumulated yield (holding short perp = collect positive funding, pay negative funding)
                raw_yield_pct = df_f['funding_rate'].sum()
                net_yield_pct = raw_yield_pct - self.entry_friction_pct
                net_apr = (net_yield_pct / years) if years > 0 else 0.0
                
                # Equity curve & drawdown computation
                equity_curve = (1.0 + df_f['funding_rate']).cumprod()
                peak = equity_curve.cummax()
                drawdown = (equity_curve - peak) / peak
                max_dd_pct = float(drawdown.min())
                
                positive_periods = (df_f['funding_rate'] > 0).mean()
                negative_periods = (df_f['funding_rate'] < 0).mean()
                
                audit_results.append({
                    "Symbol": symbol,
                    "Settlements": n_settlements,
                    "Period_Years": f"{years:.2f}",
                    "Gross_Yield": f"{raw_yield_pct*100:+.2f}%",
                    "Net_Yield": f"{net_yield_pct*100:+.2f}%",
                    "Net_APR": f"{net_apr*100:+.2f}%",
                    "Max_Drawdown": f"{max_dd_pct*100:.2f}%",
                    "Positive_Funding_Pct": f"{positive_periods*100:.1f}%",
                    "Negative_Funding_Pct": f"{negative_periods*100:.1f}%"
                })
                
        df_audit = pd.DataFrame(audit_results)
        return df_audit

if __name__ == "__main__":
    auditor = FullCycleCarryAuditor()
    df_res = auditor.run_audit()
    print("\n" + "="*80)
    print("  FULL-CYCLE DELTA-NEUTRAL CARRY AUDIT TABLE")
    print("="*80)
    print(df_res.to_string(index=False))
