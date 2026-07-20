import pandas as pd
from typing import Dict, Any
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from strategies.base_strategy import BaseStrategyAgent

class LiquidationAgent(BaseStrategyAgent):
    def __init__(self):
        super().__init__(name="LiquidationAgent")
        self.tier = "RESEARCH"

    def evaluate(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or 'oi_chg_1h' not in df.columns:
            return self._neutral(symbol, timeframe, ["Open Interest / Liquidation features missing"])

        latest = df.iloc[-1]
        reasons = []
        
        oi_chg_1h = latest.get('oi_chg_1h', 0.0)
        rsi = latest.get('rsi_14', 50.0)
        dist_ema20 = latest.get('dist_ema_20', 0.0)
        
        if oi_chg_1h < -0.005 and rsi < 32.0:
            reasons.append(f"Open Interest Flush: {oi_chg_1h*100:.2f}% drop in 1h")
            reasons.append(f"RSI Exhaustion: {rsi:.1f}")
            reasons.append(f"EMA stretch: {dist_ema20*100:.2f}%")
            
            return {
                "agent_name": self.name,
                "tier": self.tier,
                "symbol": symbol,
                "timeframe": timeframe,
                "action": "BUY",
                "confidence": 0.75,
                "expected_return_pct": 0.025,
                "expected_risk_pct": 0.012,
                "reasons": reasons
            }
            
        return self._neutral(symbol, timeframe, ["No open interest flush or exhaustion spike detected"])

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
