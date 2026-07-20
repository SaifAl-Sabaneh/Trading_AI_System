import pandas as pd
from typing import Dict, Any
from .base_strategy import BaseStrategyAgent

class CarryAgent(BaseStrategyAgent):
    def __init__(self):
        super().__init__(name="CarryAgent")

    def evaluate(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or 'funding_rate' not in df.columns:
            return self._neutral(symbol, timeframe, ["Funding rate data missing"])

        latest = df.iloc[-1]
        funding = latest.get('funding_rate', 0.0)
        funding_pctile = latest.get('funding_percentile', 0.5)
        
        # Annualized funding yield = funding_rate * 3 * 365
        annualized_yield = funding * 3 * 365
        
        reasons = []
        
        # High Positive Funding: Long Spot + Short Perp yields positive carry
        if funding > 0.00015:  # > 0.015% per 8h (~16.4% APR)
            reasons.append(f"High positive funding rate: {funding*100:.4f}% per 8h")
            reasons.append(f"Annualized Structural Carry Yield: +{annualized_yield*100:.2f}% APR")
            reasons.append(f"Funding Percentile: {funding_pctile*100:.1f}%")
            
            return {
                "agent_name": self.name,
                "symbol": symbol,
                "timeframe": timeframe,
                "action": "CARRY_DELTA_NEUTRAL",
                "confidence": 0.90,
                "expected_return_pct": annualized_yield / 365.0,  # daily yield
                "expected_risk_pct": 0.001,  # Delta neutral risk is very low
                "reasons": reasons
            }
        elif funding < -0.00015: # < -0.015% per 8h: Long Perp + Short Spot yields carry
            reasons.append(f"High negative funding rate: {funding*100:.4f}% per 8h")
            reasons.append(f"Annualized Short Carry Yield: +{abs(annualized_yield)*100:.2f}% APR")
            reasons.append(f"Funding Percentile: {funding_pctile*100:.1f}%")
            
            return {
                "agent_name": self.name,
                "symbol": symbol,
                "timeframe": timeframe,
                "action": "CARRY_REVERSE_NEUTRAL",
                "confidence": 0.90,
                "expected_return_pct": abs(annualized_yield) / 365.0,
                "expected_risk_pct": 0.001,
                "reasons": reasons
            }
            
        return self._neutral(symbol, timeframe, [f"Funding rate neutral ({funding*100:.4f}% per 8h)"])

    def _neutral(self, symbol: str, timeframe: str, reasons: list) -> Dict[str, Any]:
        return {
            "agent_name": self.name,
            "symbol": symbol,
            "timeframe": timeframe,
            "action": "NEUTRAL",
            "confidence": 0.50,
            "expected_return_pct": 0.0,
            "expected_risk_pct": 0.0,
            "reasons": reasons
        }
