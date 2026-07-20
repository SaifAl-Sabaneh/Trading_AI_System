import pandas as pd
import numpy as np

class VolumeFeatureExtractor:
    @staticmethod
    def compute_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Volume Change
        df['volume_change'] = df['volume'].pct_change(periods=1)
        
        # Volume Z-score (50-bar rolling)
        vol_mean = df['volume'].rolling(50, min_periods=10).mean()
        vol_std  = df['volume'].rolling(50, min_periods=10).std()
        df['volume_zscore'] = (df['volume'] - vol_mean) / (vol_std + 1e-9)
        
        # Volume Breakout Ratio (Current Volume / 20-bar Volume SMA)
        vol_sma_20 = df['volume'].rolling(20, min_periods=5).mean()
        df['volume_breakout'] = df['volume'] / (vol_sma_20 + 1e-9)
        
        return df

if __name__ == "__main__":
    print("VolumeFeatureExtractor module ready.")
