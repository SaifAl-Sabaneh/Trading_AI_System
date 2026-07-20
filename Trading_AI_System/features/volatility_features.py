import pandas as pd
import numpy as np

class VolatilityFeatureExtractor:
    @staticmethod
    def compute_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # ATR (14)
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        df['atr_14'] = tr.rolling(window=14, min_periods=14).mean()
        df['volatility_pct'] = df['atr_14'] / (df['close'] + 1e-9)
        
        # Realized Volatility (20-bar standard deviation of log returns)
        log_rets = np.log(df['close'] / df['close'].shift(1))
        df['realized_vol_20'] = log_rets.rolling(20, min_periods=5).std() * np.sqrt(288) # annualized approximation
        
        # Volatility Percentile (100-bar window)
        df['vol_percentile'] = df['volatility_pct'].rolling(100, min_periods=10).apply(
            lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min() + 1e-9) if x.max() != x.min() else 0.5
        )
        
        # Volatility Expansion (Current ATR / 50-bar ATR SMA)
        atr_sma_50 = df['atr_14'].rolling(50, min_periods=10).mean()
        df['vol_expansion'] = df['atr_14'] / (atr_sma_50 + 1e-9)
        
        return df

if __name__ == "__main__":
    print("VolatilityFeatureExtractor module ready.")
