import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

class MarketStateClassifier:
    @staticmethod
    def classify(df: pd.DataFrame) -> Tuple[str, str, str, str, float]:
        """
        Input: DataFrame containing enriched price, volatility, and volume features.
        Returns: (trend_state, volatility_state, liquidity_state, risk_state, regime_score)
        """
        if df.empty or len(df) < 20:
            return "NEUTRAL", "NORMAL", "NORMAL", "MEDIUM", 0.0

        latest = df.iloc[-1]
        close = latest['close']
        
        # 1. Trend Classification
        dist_ema20 = latest.get('dist_ema_20', 0.0)
        dist_ema50 = latest.get('dist_ema_50', 0.0)
        dist_ema200 = latest.get('dist_ema_200', 0.0)
        
        if dist_ema20 > 0.01 and dist_ema50 > 0.02 and dist_ema200 > 0.03:
            trend_state = "STRONG_UPTREND"
            trend_score = 0.8
        elif dist_ema20 > 0.0:
            trend_state = "WEAK_UPTREND"
            trend_score = 0.3
        elif dist_ema20 < -0.01 and dist_ema50 < -0.02 and dist_ema200 < -0.03:
            trend_state = "STRONG_DOWNTREND"
            trend_score = -0.8
        elif dist_ema20 < 0.0:
            trend_state = "WEAK_DOWNTREND"
            trend_score = -0.3
        else:
            trend_state = "NEUTRAL"
            trend_score = 0.0

        # 2. Volatility Classification
        vol_pctile = latest.get('vol_percentile', 0.5)
        vol_expansion = latest.get('vol_expansion', 1.0)
        
        if vol_pctile > 0.90 or vol_expansion > 2.0:
            vol_state = "EXTREME"
        elif vol_pctile > 0.70 or vol_expansion > 1.3:
            vol_state = "HIGH"
        elif vol_pctile < 0.25:
            vol_state = "LOW"
        else:
            vol_state = "NORMAL"

        # 3. Liquidity Classification
        vol_breakout = latest.get('volume_breakout', 1.0)
        if vol_breakout > 1.8:
            liq_state = "SURGE"
        elif vol_breakout < 0.5:
            liq_state = "DRY"
        else:
            liq_state = "NORMAL"

        # 4. Risk Classification
        if vol_state == "EXTREME":
            risk_state = "EXTREME"
        elif vol_state == "HIGH" or liq_state == "DRY":
            risk_state = "HIGH"
        elif vol_state == "LOW" and trend_state in ["STRONG_UPTREND", "WEAK_UPTREND"]:
            risk_state = "LOW"
        else:
            risk_state = "MEDIUM"

        regime_score = float(np.clip(trend_score, -1.0, 1.0))
        return trend_state, vol_state, liq_state, risk_state, regime_score

if __name__ == "__main__":
    print("MarketStateClassifier module ready.")
