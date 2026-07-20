import os
import sys
import pandas as pd
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database
from features.technical_features import TechnicalFeatureExtractor
from features.derivative_features import DerivativeFeatureExtractor

# SHADOW COLLECTOR: Imports research agents strictly for logging observations to trade_memory
from strategies.research import MomentumAgent, MeanReversionAgent, LiquidationAgent

class ShadowEngine:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()
        self.research_agents = [
            MomentumAgent(),
            MeanReversionAgent(),
            LiquidationAgent()
        ]

    def process_shadow_observations(self, symbols: List[str], timeframe: str = "1h") -> List[Dict[str, Any]]:
        observations = []
        for symbol in symbols:
            candles = self.db.fetch_candles(symbol, timeframe)
            if not candles:
                continue
            cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df = pd.DataFrame([c[:6] for c in candles], columns=cols)
            df = TechnicalFeatureExtractor.compute_features(df)
            
            with self.db.get_connection() as conn:
                df_funding = pd.read_sql("SELECT timestamp, funding_rate, mark_price FROM funding_rates WHERE symbol = ?", conn, params=[symbol])
                df_oi = pd.read_sql("SELECT timestamp, open_interest, open_interest_usd FROM open_interest WHERE symbol = ?", conn, params=[symbol])
                
            df = DerivativeFeatureExtractor.compute_features(df, df_funding, df_oi)
            
            for agent in self.research_agents:
                dec = agent.evaluate(symbol, timeframe, df)
                if dec["action"] != "NEUTRAL":
                    observations.append(dec)
                    
        return observations

if __name__ == "__main__":
    shadow = ShadowEngine()
    print("ShadowEngine loaded successfully.")
    print("Shadow Research Agents (Quarantined Shadow Mode):", [a.name for a in shadow.research_agents])
