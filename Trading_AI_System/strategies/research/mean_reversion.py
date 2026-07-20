import pandas as pd
from typing import Dict, Any
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from strategies.base_strategy import BaseStrategyAgent

class MeanReversionAgent(BaseStrategyAgent):
    def __init__(self):
        super().__init__(name="MeanReversionAgent")
        self.tier = "RESEARCH"

    def evaluate(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or len(df) < 50:
            return self._neutral(symbol, timeframe, ["Insufficient data"])

        latest = df.iloc[-1]
        reasons = []
        
        rsi = latest.get('rsi_14', 50.0)
        dist_ema20 = latest.get('dist_ema_20', 0.0)
        vol_pct = latest.get('volatility_pct', 0.01)
        
        if rsi < 30.0 and dist_ema20 < -0.02:
            reasons.append(f"RSI Oversold: {rsi:.1f}")
            reasons.append(f"Distance to 20-EMA stretched: {dist_ema20*100:.2f}%")
            confidence = 0.70
            if rsi < 25.0:
                confidence += 0.10
                
            return {
                "agent_name": self.name,
                "tier": self.tier,
                "symbol": symbol,
                "timeframe": timeframe,
                "action": "BUY",
                "confidence": min(confidence, 0.85),
                "expected_return_pct": abs(dist_ema20),
                "expected_risk_pct": vol_pct * 1.5,
                "reasons": reasons
            }
        elif rsi > 70.0 and dist_ema20 > 0.02:
            reasons.append(f"RSI Overbought: {rsi:.1f}")
            reasons.append(f"Distance to 20-EMA stretched: +{dist_ema20*100:.2f}%")
            confidence = 0.70
            if rsi > 75.0:
                confidence += 0.10
                
            return {
                "agent_name": self.name,
                "tier": self.tier,
                "symbol": symbol,
                "timeframe": timeframe,
                "action": "SELL",
                "confidence": min(confidence, 0.85),
                "expected_return_pct": abs(dist_ema20),
                "expected_risk_pct": vol_pct * 1.5,
                "reasons": reasons
            }
            
        return self._neutral(symbol, timeframe, ["RSI and EMA distance within normal bands"])

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
