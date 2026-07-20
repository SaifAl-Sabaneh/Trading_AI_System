import pandas as pd
import numpy as np
from typing import Dict, Any

class TechnicalFeatureExtractor:
    @staticmethod
    def compute_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Expects df with columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        Returns df enriched with normalized technical feature columns.
        """
        df = df.copy()
        
        # 1. EMAs and Distances
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        df['dist_ema_20'] = (df['close'] - df['ema_20']) / df['ema_20']
        df['dist_ema_50'] = (df['close'] - df['ema_50']) / df['ema_50']
        df['dist_ema_200'] = (df['close'] - df['ema_200']) / df['ema_200']
        
        # 2. EMA Slopes (5-bar slope)
        df['ema_20_slope'] = df['ema_20'].pct_change(periods=5)
        
        # 3. RSI (14)
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -1 * delta.clip(upper=0)
        avg_gain = gain.rolling(window=14, min_periods=14).mean()
        avg_loss = loss.rolling(window=14, min_periods=14).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        df['rsi_14'] = 100.0 - (100.0 / (1.0 + rs))
        
        # 4. ATR (14) and Volatility %
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr_14'] = tr.rolling(window=14, min_periods=14).mean()
        df['volatility_pct'] = df['atr_14'] / df['close']
        
        # 5. Volume Anomaly Ratio
        vol_sma_20 = df['volume'].rolling(window=20, min_periods=5).mean()
        df['rel_volume'] = df['volume'] / (vol_sma_20 + 1e-9)
        
        return df

if __name__ == "__main__":
    # Quick sanity test
    sample_data = pd.DataFrame({
        'timestamp': range(100),
        'open': np.linspace(100, 110, 100),
        'high': np.linspace(101, 111, 100),
        'low': np.linspace(99, 109, 100),
        'close': np.linspace(100.5, 110.5, 100),
        'volume': np.random.uniform(10, 50, 100)
    })
    feat_df = TechnicalFeatureExtractor.compute_features(sample_data)
    print("Features extracted successfully. Columns:")
    print(feat_df.columns.tolist())
