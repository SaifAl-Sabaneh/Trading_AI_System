import pandas as pd
import numpy as np
from scipy import stats
import os
import matplotlib.pyplot as plt

def calculate_ofi(df, interval_str):
    # Convert 'time' to datetime and set as index
    # We copy to avoid modifying the original dataframe
    temp = df.copy()
    temp['datetime'] = pd.to_datetime(temp['time'], unit='ms')
    temp.set_index('datetime', inplace=True)
    
    # Calculate aggressive volume (USD value)
    # If is_buyer_maker is True: Taker was Seller -> Aggressive Sell (negative volume)
    # If is_buyer_maker is False: Taker was Buyer -> Aggressive Buy (positive volume)
    temp['agg_vol_usd'] = np.where(temp['is_buyer_maker'], -temp['quote_qty'], temp['quote_qty'])
    
    # Resample to group by the interval
    # OFI = sum of aggressive volume (USD) in the interval
    ofi_series = temp['agg_vol_usd'].resample(interval_str).sum()
    
    # We also need the close price of each interval to calculate forward returns
    price_series = temp['price'].resample(interval_str).last()
    
    # Forward fill price in case of empty intervals
    price_series.ffill(inplace=True)
    
    # Combine into a single feature dataframe
    feature_df = pd.DataFrame({
        'ofi': ofi_series,
        'close_price': price_series
    })
    
    return feature_df

def run_ofi_screening(file_path):
    print("=" * 80)
    print("  RUNNING OFI FEATURE PRE-SCREENING AUDIT")
    print("=" * 80)
    
    # 1. Load data
    print(f"Loading {file_path}...")
    df = pd.read_csv(file_path)
    
    # 2. Define configurations: (Feature_Interval, Fwd_Horizon_Interval, Horizon_Label)
    configs = [
        ('1min', '15min', 15),   # 1m OFI predicting 15m return
        ('5min', '60min', 12),   # 5m OFI predicting 1h return
        ('15min', '240min', 16)  # 15m OFI predicting 4h return
    ]
    
    screening_results = []
    
    for feat_int, fwd_int, steps in configs:
        print(f"\nAnalyzing Configuration: Feature = {feat_int} | Fwd Horizon = {fwd_int} ({steps} steps ahead)...")
        
        # Calculate OFI and price series
        feat_df = calculate_ofi(df, feat_int)
        
        # Calculate forward returns: (Price_{t + steps} - Price_t) / Price_t * 100
        feat_df['fwd_return'] = feat_df['close_price'].pct_change(periods=steps).shift(-steps) * 100
        
        # Drop NaNs from forward returns (at the end of the series)
        clean_df = feat_df.dropna(subset=['ofi', 'fwd_return'])
        
        if len(clean_df) < 30:
            print("  [SKIP] Too few samples to calculate correlation.")
            continue
            
        # 3. Calculate Information Coefficient (IC) - Spearman Rank Correlation
        ic, p_value = stats.spearmanr(clean_df['ofi'], clean_df['fwd_return'])
        
        # 4. Run Permutation (Shuffle) Test (1,000 runs)
        # We shuffle the returns to check if our IC is just random noise
        null_ics = []
        shuffled_returns = clean_df['fwd_return'].values.copy()
        
        for _ in range(1000):
            np.random.shuffle(shuffled_returns)
            perm_ic, _ = stats.spearmanr(clean_df['ofi'], shuffled_returns)
            null_ics.append(perm_ic)
            
        # Calculate empirical p-value (how many random shuffles produced a larger absolute IC than ours?)
        empirical_p = (np.abs(null_ics) >= np.abs(ic)).mean()
        
        # 5. Stability Check (Split day into 4 chunks and calculate IC for each)
        chunk_size = len(clean_df) // 4
        chunks = [clean_df.iloc[i * chunk_size : (i + 1) * chunk_size] for i in range(4)]
        chunk_ics = []
        for i, chunk in enumerate(chunks):
            if len(chunk) > 5:
                c_ic, _ = stats.spearmanr(chunk['ofi'].values, chunk['fwd_return'].values)
                chunk_ics.append(c_ic)
            else:
                chunk_ics.append(np.nan)
                
        # Check if the sign is stable (all positive or all negative)
        signs = [np.sign(c) for c in chunk_ics if not np.isnan(c)]
        is_stable = len(set(signs)) == 1 if len(signs) > 0 else False
        
        # Pre-registered Hurdle Checks:
        # - Absolute IC >= 0.03
        # - Empirical p-value < 0.05
        # - Directional Stability = True
        pass_ic = abs(ic) >= 0.03
        pass_p = empirical_p < 0.05
        
        verdict = "PASS" if (pass_ic and pass_p and is_stable) else "FAIL"
        
        print(f"  Sample Size (n):      {len(clean_df)}")
        print(f"  Information Coeff:    {ic:+.6f} (Hurdle >= 0.03: {'PASS' if pass_ic else 'FAIL'})")
        print(f"  Empirical p-value:    {empirical_p:.6f} (Hurdle < 0.05: {'PASS' if pass_p else 'FAIL'})")
        print(f"  Stability by Chunk:   {['%+.4f' % c for c in chunk_ics]} (Stable: {is_stable})")
        print(f"  Screening Verdict:    **{verdict}**")
        
        screening_results.append({
            'config': f"{feat_int} -> {fwd_int}",
            'ic': ic,
            'p_value': empirical_p,
            'stable': is_stable,
            'verdict': verdict
        })
        
    print("\n" + "=" * 80)
    print("  FINAL PRE-SCREENING SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Configuration':<25} | {'Information Coeff':<20} | {'p-value':<15} | {'Stable?':<10} | {'Verdict':<10}")
    print("-" * 80)
    for res in screening_results:
        print(f"{res['config']:<25} | {res['ic'] :+20.6f} | {res['p_value']:<15.6f} | {str(res['stable']):<10} | {res['verdict']:<10}")
    print("=" * 80)

if __name__ == '__main__':
    csv_path = "SOLUSDT-trades-2026-07-15.csv"
    if os.path.exists(csv_path):
        run_ofi_screening(csv_path)
    else:
        print(f"Error: {csv_path} not found. Please run download_and_check_trades.py first.")
