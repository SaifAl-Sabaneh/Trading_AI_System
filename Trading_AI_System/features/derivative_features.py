import pandas as pd
import numpy as np

class DerivativeFeatureExtractor:
    @staticmethod
    def compute_features(df_candles: pd.DataFrame, df_funding: pd.DataFrame, df_oi: pd.DataFrame) -> pd.DataFrame:
        """
        Merges candles with funding rates and open interest, computing normalized derivatives metrics.
        Computes rolling funding percentile directly on the funding rate series (8h settlements) before merging.
        """
        df = df_candles.copy()
        
        # Merge Funding Rates
        if not df_funding.empty:
            df_f = df_funding.sort_values('timestamp').copy()
            # Compute 100-settlement rolling percentile on 8h funding rate series (~33 days)
            df_f['funding_rate_pctile'] = df_f['funding_rate'].rolling(100, min_periods=10).apply(
                lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min() + 1e-9) if x.max() != x.min() else 0.5
            )
            df = pd.merge_asof(df.sort_values('timestamp'), 
                               df_f[['timestamp', 'funding_rate', 'funding_rate_pctile', 'mark_price']], 
                               on='timestamp', direction='backward')
            df['funding_rate'] = df['funding_rate'].fillna(0.0)
            df['funding_rate_pctile'] = df['funding_rate_pctile'].fillna(0.5)
        else:
            df['funding_rate'] = 0.0
            df['funding_rate_pctile'] = 0.5
            
        # Merge Open Interest
        if not df_oi.empty:
            df_oi_clean = df_oi.sort_values('timestamp').copy()
            df = pd.merge_asof(df.sort_values('timestamp'), 
                               df_oi_clean[['timestamp', 'open_interest', 'open_interest_usd']], 
                               on='timestamp', direction='backward')
            df['open_interest'] = df['open_interest'].fillna(0.0)
            df['oi_chg_1h'] = df['open_interest'].pct_change(periods=1).fillna(0.0)
            df['oi_chg_4h'] = df['open_interest'].pct_change(periods=4).fillna(0.0)
            oi_roll = df['open_interest'].rolling(30, min_periods=5)
            std = oi_roll.std().fillna(0.0)
            mean = oi_roll.mean().fillna(0.0)
            df['oi_zscore'] = np.where(std > 1e-9, (df['open_interest'] - mean) / (std + 1e-9), 0.0)
        else:
            df['open_interest'] = 0.0
            df['oi_chg_1h'] = 0.0
            df['oi_chg_4h'] = 0.0
            df['oi_zscore'] = 0.0
            
        return df

if __name__ == "__main__":
    print("DerivativeFeatureExtractor defined successfully.")
