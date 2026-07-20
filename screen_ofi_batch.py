import pandas as pd
import numpy as np
from scipy import stats
import os
from datetime import datetime, timedelta

def calculate_ofi(df, interval_str):
    temp = df.copy()
    temp['datetime'] = pd.to_datetime(temp['time'], unit='ms')
    temp.set_index('datetime', inplace=True)
    temp['agg_vol_usd'] = np.where(temp['is_buyer_maker'], -temp['quote_qty'], temp['quote_qty'])
    
    ofi_series = temp['agg_vol_usd'].resample(interval_str).sum()
    price_series = temp['price'].resample(interval_str).last()
    price_series.ffill(inplace=True)
    
    feature_df = pd.DataFrame({
        'ofi': ofi_series,
        'close_price': price_series
    })
    return feature_df

def run_batch_ofi_screening(symbol="SOLUSDT", start_date="2026-07-10", end_date="2026-07-16", exclude_weekends=True):
    print("=" * 80)
    print(f"  RUNNING BATCH OFI FEATURE SCREENING (7-DAY LARGE SAMPLE)")
    print(f"  Filter: Exclude Weekends = {exclude_weekends}")
    print("=" * 80)
    
    # Generate date range
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    current_dt = start_dt
    
    combined_15m_dfs = []
    
    # Process each day
    while current_dt <= end_dt:
        date_str = current_dt.strftime("%Y-%m-%d")
        csv_file = f"{symbol}-trades-{date_str}.csv"
        
        # Check if weekend (Saturday = 5, Sunday = 6)
        if exclude_weekends and current_dt.weekday() in [5, 6]:
            print(f"Skipping {date_str} (Weekend)...")
            current_dt += timedelta(days=1)
            continue
            
        if os.path.exists(csv_file):
            print(f"Processing {csv_file}...")
            day_df = pd.read_csv(csv_file)
            
            # Resample to 15m intervals
            day_15m = calculate_ofi(day_df, "15min")
            combined_15m_dfs.append(day_15m)
        else:
            print(f"  [WARN] {csv_file} not found. Skipping.")
            
        current_dt += timedelta(days=1)
        
    if not combined_15m_dfs:
        print("[ERROR] No daily trade files found. Please run download_batch_trades.py first.")
        return
        
    # Concatenate all 15m dataframes
    full_df = pd.concat(combined_15m_dfs).sort_index()
    
    # Calculate 4-hour forward returns (16 steps of 15m)
    # R_fwd = (Price_{t + 16} - Price_t) / Price_t * 100
    steps = 16
    full_df['fwd_return'] = full_df['close_price'].pct_change(periods=steps).shift(-steps) * 100
    
    # Drop NaNs
    clean_df = full_df.dropna(subset=['ofi', 'fwd_return'])
    
    print("\n" + "-" * 80)
    print("  LARGE SAMPLE SCREENING ANALYSIS (15min OFI -> 4h Return)")
    print("-" * 80)
    print(f"Total Combined Intervals (n): {len(clean_df)}")
    
    # 1. Spearman Rank Information Coefficient (IC)
    ic, p_val_stat = stats.spearmanr(clean_df['ofi'].values, clean_df['fwd_return'].values)
    
    # 2. 1,000-run Permutation (Shuffle) Test
    null_ics = []
    shuffled_returns = clean_df['fwd_return'].values.copy()
    for _ in range(1000):
        np.random.shuffle(shuffled_returns)
        perm_ic, _ = stats.spearmanr(clean_df['ofi'].values, shuffled_returns)
        null_ics.append(perm_ic)
        
    empirical_p = (np.abs(null_ics) >= np.abs(ic)).mean()
    
    # 3. Stability Check (Split 7-day dataset into 4 chronological chunks)
    chunk_size = len(clean_df) // 4
    chunks = [clean_df.iloc[i * chunk_size : (i+1) * chunk_size] for i in range(4)]
    chunk_ics = []
    for i, chunk in enumerate(chunks):
        c_ic, _ = stats.spearmanr(chunk['ofi'].values, chunk['fwd_return'].values)
        chunk_ics.append(c_ic)
        
    signs = [np.sign(c) for c in chunk_ics]
    is_stable = len(set(signs)) == 1
    
    # 4. Hurdle Checks
    pass_ic = abs(ic) >= 0.03
    pass_p = empirical_p < 0.05
    
    verdict = "PASS" if (pass_ic and pass_p and is_stable) else "FAIL"
    
    print(f"  Information Coeff:    {ic:+.6f} (Hurdle >= 0.03: {'PASS' if pass_ic else 'FAIL'})")
    print(f"  Empirical p-value:    {empirical_p:.6f} (Hurdle < 0.05: {'PASS' if pass_p else 'FAIL'})")
    print(f"  Stability by Chunk:   {['%+.4f' % c for c in chunk_ics]} (Stable: {is_stable})")
    print(f"  Final Decision:       **{verdict}**")
    print("-" * 80)
    
if __name__ == '__main__':
    run_batch_ofi_screening()
