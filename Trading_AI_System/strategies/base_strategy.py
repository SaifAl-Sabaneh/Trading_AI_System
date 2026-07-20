from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, List

class BaseStrategyAgent(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def evaluate(self, symbol: str, timeframe: str, df_features: pd.DataFrame) -> Dict[str, Any]:
        """
        Evaluates current market features and returns a standardized decision dict:
        {
            "agent_name": str,
            "symbol": str,
            "timeframe": str,
            "action": "BUY" | "SELL" | "NEUTRAL",
            "confidence": float (0.0 to 1.0),
            "expected_return_pct": float,
            "expected_risk_pct": float,
            "reasons": List[str]
        }
        """
        pass
