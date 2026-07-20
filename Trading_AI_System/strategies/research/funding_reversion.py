import pandas as pd
import numpy as np
from typing import Dict, Any
from strategies.base_strategy import BaseStrategyAgent

class FundingReversionAgent(BaseStrategyAgent):
    """
    HYP-FUND-REV-V1: Funding Rate Extreme Reversion & Leverage Unwind Agent
    Quarantined in Research Sandbox (Tier: RESEARCH)
    """
    def __init__(self, name: str = "FundingReversionAgent"):
        super().__init__(name=name)
        self.tier = "RESEARCH"
        self.min_funding_pctile = 0.90
        self.min_funding_rate = 0.0003  # +0.03% per 8h
        self.min_oi_zscore = 1.0

    def _build_decision(self, symbol: str, timeframe: str, action: str, confidence: float, reasons: list, exp_ret: float = 0.025, exp_risk: float = 0.012) -> Dict[str, Any]:
        return {
            "agent_name": self.name,
            "symbol": symbol,
            "timeframe": timeframe,
            "action": action,
            "confidence": confidence,
            "expected_return_pct": exp_ret,
            "expected_risk_pct": exp_risk,
            "reasons": reasons
        }

    def evaluate(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or len(df) < 30:
            return self._build_decision(symbol, timeframe, "NEUTRAL", 0.0, ["Insufficient candles"])
            
        latest = df.iloc[-1]
        
        funding_rate = float(latest.get("funding_rate", 0.0))
        funding_pctile = float(latest.get("funding_rate_pctile", 0.50))
        oi_zscore = float(latest.get("oi_zscore", 0.0))
        
        reasons = []
        oi_ok = (oi_zscore >= self.min_oi_zscore) if oi_zscore != 0.0 else True
        
        # Pre-registered Entry Condition: Extreme Long Crowding (SHORT Signal)
        if funding_rate >= 0.0008 and funding_pctile >= self.min_funding_pctile and oi_ok:
            confidence = min(0.85, 0.65 + (funding_pctile - 0.90) * 2.0)
            reasons.append(f"Funding Rate Extreme: {funding_rate*100:.4f}%/8h (Percentile: {funding_pctile*100:.1f}%)")
            reasons.append(f"OI Z-Score: {oi_zscore:.2f}")
            reasons.append("Leverage crowding reversal signal")
            return self._build_decision(symbol, timeframe, "SELL", confidence, reasons, 0.025, 0.012)
            
        # Reverse: Extreme Short Crowding (BUY Signal)
        elif funding_rate <= -0.0008 and funding_pctile <= (1.0 - self.min_funding_pctile) and oi_ok:
            confidence = min(0.85, 0.65 + (0.10 - funding_pctile) * 2.0)
            reasons.append(f"Negative Funding Rate Extreme: {funding_rate*100:.4f}%/8h (Percentile: {funding_pctile*100:.1f}%)")
            reasons.append(f"OI Z-Score: {oi_zscore:.2f}")
            reasons.append("Short squeeze reversal signal")
            return self._build_decision(symbol, timeframe, "BUY", confidence, reasons, 0.025, 0.012)

        return self._build_decision(symbol, timeframe, "NEUTRAL", 0.0, ["Funding & OI within normal limits"])

if __name__ == "__main__":
    agent = FundingReversionAgent()
    print(f"Agent Initialized: {agent.name} (Tier: {agent.tier})")
