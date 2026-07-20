import pandas as pd
import numpy as np

class PriceFeatureExtractor:
    @staticmethod
    def compute_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Multi-horizon returns
        df['return_5m']  = df['close'].pct_change(periods=1)
        df['return_15m'] = df['close'].pct_change(periods=3)
        df['return_1h']  = df['close'].pct_change(periods=12)
        df['return_4h']  = df['close'].pct_change(periods=48)
        df['return_24h'] = df['close'].pct_change(periods=288)
        
        # Distance from rolling High/Low (24h window = 288 5m bars)
        roll_high_24h = df['high'].rolling(288, min_periods=12).max()
        roll_low_24h  = df['low'].rolling(288, min_periods=12).min()
        
        df['dist_from_high_24h'] = (df['close'] - roll_high_24h) / (roll_high_24h + 1e-9)
        df['dist_from_low_24h']  = (df['close'] - roll_low_24h) / (roll_low_24h + 1e-9)
        
        return df

if __name__ == "__main__":
    print("PriceFeatureExtractor module ready.")
