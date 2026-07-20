import pandas as pd
from typing import Dict, Any
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from strategies.base_strategy import BaseStrategyAgent

class CarryAgent(BaseStrategyAgent):
    """
    Production Carry Agent (HYP-CARRY-V1)
    
    Production Rules (Validated via 3.75-Year Full-Cycle Audit):
    1. Major Caps Only: Restricted strictly to BTCUSDT and ETHUSDT. Altcoins banned.
    2. Negative Funding Exit: Exit / Neutral when funding rate <= 0 to eliminate bear cascade tail risk.
    3. Minimum Funding Hurdle: Positive funding rate >= +0.0001 (0.01%/8h or ~11% APR).
    """
    def __init__(self):
        super().__init__(name="CarryAgent")
        self.tier = "PRODUCTION"
        self.allowed_symbols = ["BTCUSDT", "ETHUSDT"]
        self.min_funding_threshold = 0.0001  # +0.01% per 8h (~11% APR)

    def evaluate(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Dict[str, Any]:
        # Rule 1: Major Caps Only Guard
        if symbol not in self.allowed_symbols:
            return self._neutral(symbol, timeframe, [f"Symbol {symbol} banned from carry pool (Major caps BTC/ETH only)"])

        if df.empty or 'funding_rate' not in df.columns:
            return self._neutral(symbol, timeframe, ["Funding rate data missing"])

        latest = df.iloc[-1]
        funding = float(latest.get('funding_rate', 0.0))
        funding_pctile = float(latest.get('funding_rate_pctile', latest.get('funding_percentile', 0.5)))
        
        annualized_yield = funding * 3 * 365
        reasons = []
        
        # Rule 2: Positive Funding Entry / Rule 3: Minimum Hurdle
        if funding >= self.min_funding_threshold:
            reasons.append(f"Positive funding rate: {funding*100:.4f}% per 8h")
            reasons.append(f"Annualized Structural Carry Yield: +{annualized_yield*100:.2f}% APR")
            reasons.append(f"Funding Percentile: {funding_pctile*100:.1f}%")
            reasons.append("Delta-Neutral Long Spot + Short Perp Allocation Authorized")
            
            return {
                "agent_name": self.name,
                "tier": self.tier,
                "symbol": symbol,
                "timeframe": timeframe,
                "action": "CARRY_DELTA_NEUTRAL",
                "confidence": 0.95,
                "expected_return_pct": annualized_yield / 365.0,
                "expected_risk_pct": 0.0005,
                "reasons": reasons
            }
        # Negative Funding Exit Guard: Exit position immediately if funding turns negative/neutral
        elif funding < 0.0:
            return self._neutral(symbol, timeframe, [
                f"Negative funding rate ({funding*100:.4f}% per 8h). Exit position to avoid holding cost drag."
            ])
            
        return self._neutral(symbol, timeframe, [f"Funding rate neutral ({funding*100:.4f}% per 8h)"])

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

if __name__ == "__main__":
    agent = CarryAgent()
    print(f"Production Agent Initialized: {agent.name} (Tier: {agent.tier})")
    print(f"Allowed Assets: {agent.allowed_symbols}")
