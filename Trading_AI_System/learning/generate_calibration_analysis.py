import os
import sys
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database

def main():
    db = Database()
    with db.get_connection() as conn:
        df_stats = pd.read_sql("SELECT * FROM strategy_statistics;", conn)
        df_mem = pd.read_sql("SELECT * FROM trade_memory WHERE evaluated_at IS NOT NULL;", conn)
        
    print("============================================================")
    print("  STRATEGY CALIBRATION & MEASUREMENT REPORT")
    print("============================================================")
    
    print(f"\n1. Overall Dataset Summary:")
    print(f"   - Total Evaluated Decisions: {len(df_mem)}")
    print(f"   - Total Calibration Groups:  {len(df_stats)}")
    
    print("\n2. Confidence Calibration by Agent (Confidence Bucket vs Actual Win Rate):")
    calib_grp = df_stats.groupby(['strategy_name', 'confidence_bucket']).agg({
        'n_decisions': 'sum',
        'win_rate': 'mean',
        'mean_return_pct': 'mean',
        'profit_factor': 'mean',
        'avg_mfe_pct': 'mean',
        'avg_mae_pct': 'mean',
        'calibrated_accuracy': 'mean'
    }).reset_index()
    
    for idx, row in calib_grp.iterrows():
        status = "CALIBRATED" if row['calibrated_accuracy'] >= 0 else "OVERCONFIDENT"
        print(f"   [{row['strategy_name']}] Bucket {row['confidence_bucket']} (n={row['n_decisions']}):")
        print(f"     • Win Rate:        {row['win_rate']*100:.1f}%")
        print(f"     • Mean 24h Return: {row['mean_return_pct']*100:.2f}%")
        print(f"     • Profit Factor:   {row['profit_factor']:.2f}")
        print(f"     • Avg MFE / MAE:   +{row['avg_mfe_pct']*100:.2f}% / {row['avg_mae_pct']*100:.2f}%")
        print(f"     • Calibration:     {status} (Diff: {row['calibrated_accuracy']*100:+.1f}%)")
        print()

    print("============================================================")
    print("  PROMOTION / DEMOTION STATUS")
    print("============================================================")
    agents = df_stats['strategy_name'].unique()
    for agent in agents:
        agent_df = df_stats[df_stats['strategy_name'] == agent]
        avg_ret = agent_df['mean_return_pct'].mean()
        avg_pf = agent_df['profit_factor'].mean()
        win_rate = agent_df['win_rate'].mean()
        
        if avg_ret > 0 and avg_pf > 1.2:
            verdict = "PROMOTED (Passed Calibration Hurdle)"
        else:
            verdict = "DEMOTED (Kept in Research Sandbox - Failed Expectancy Hurdle)"
            
        print(f"  * {agent}: {verdict}")
        print(f"    - Avg Win Rate: {win_rate*100:.1f}% | Mean Return: {avg_ret*100:+.2f}% | Profit Factor: {avg_pf:.2f}")

if __name__ == "__main__":
    main()
