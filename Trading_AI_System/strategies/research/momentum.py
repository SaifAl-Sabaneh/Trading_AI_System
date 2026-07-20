import pandas as pd
from typing import Dict, Any
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from strategies.base_strategy import BaseStrategyAgent

class MomentumAgent(BaseStrategyAgent):
    def __init__(self):
        super().__init__(name="MomentumAgent")
        self.tier = "RESEARCH"

    def evaluate(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or len(df) < 50:
            return self._neutral(symbol, timeframe, ["Insufficient data"])

        latest = df.iloc[-1]
        reasons = []
        
        close = latest['close']
        ema20 = latest.get('ema_20', close)
        ema50 = latest.get('ema_50', close)
        ema200 = latest.get('ema_200', close)
        rel_vol = latest.get('rel_volume', 1.0)
        slope_20 = latest.get('ema_20_slope', 0.0)
        
        bull_stack = (close > ema20) and (ema20 > ema50) and (ema50 > ema200)
        strong_slope = slope_20 > 0.002
        vol_surge = rel_vol > 1.2
        
        bear_stack = (close < ema20) and (ema20 < ema50) and (ema50 < ema200)
        neg_slope = slope_20 < -0.002
        
        if bull_stack and strong_slope:
            reasons.append("EMA Alignment: Bullish stack (Price > 20 > 50 > 200)")
            reasons.append(f"Strong 20-EMA slope: +{slope_20*100:.2f}%")
            confidence = 0.65
            if vol_surge:
                reasons.append(f"Volume surge detected ({rel_vol:.2f}x average)")
                confidence += 0.10
                
            return {
                "agent_name": self.name,
                "tier": self.tier,
                "symbol": symbol,
                "timeframe": timeframe,
                "action": "BUY",
                "confidence": min(confidence, 0.90),
                "expected_return_pct": 0.025,
                "expected_risk_pct": 0.012,
                "reasons": reasons
            }
        elif bear_stack and neg_slope:
            reasons.append("EMA Alignment: Bearish stack (Price < 20 < 50 < 200)")
            reasons.append(f"Negative 20-EMA slope: {slope_20*100:.2f}%")
            confidence = 0.65
            if vol_surge:
                reasons.append(f"Volume surge detected ({rel_vol:.2f}x average)")
                confidence += 0.10
                
            return {
                "agent_name": self.name,
                "tier": self.tier,
                "symbol": symbol,
                "timeframe": timeframe,
                "action": "SELL",
                "confidence": min(confidence, 0.90),
                "expected_return_pct": 0.025,
                "expected_risk_pct": 0.012,
                "reasons": reasons
            }
            
        return self._neutral(symbol, timeframe, ["No clear trend alignment"])

    def _neutral(self, symbol: str, timeframe: str, reasons: list) -> Dict[str, Any]:
        return {
            "agent_name": self.name,
            "tier": self.tier,
            "symbol": symbol,
            "timeframe": timeframe,
            "action": "NEUTRAL",
            "confidence": 0.50,
            "expected_return_pct": 0.0,
            "expected_risk_pct": 0.0,
            "reasons": reasons
        }
