import os
import sys
import pandas as pd
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import DatabaseManager
from features.technical_features import TechnicalFeatureExtractor
from features.derivative_features import DerivativeFeatureExtractor
from strategies.momentum_agent import MomentumAgent
from strategies.mean_reversion_agent import MeanReversionAgent
from strategies.carry_agent import CarryAgent
from engine.risk_engine import RiskEngine

class DecisionEngine:
    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager if db_manager else DatabaseManager()
        self.risk_engine = RiskEngine()
        
        # Instantiate Specialist Agents
        self.agents = [
            MomentumAgent(),
            MeanReversionAgent(),
            CarryAgent()
        ]

    def process_asset(self, symbol: str, timeframe: str = "1h") -> List[Dict[str, Any]]:
        # Fetch data
        candles = self.db.fetch_candles(symbol, timeframe)
        if not candles:
            return []
            
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame([c[:6] for c in candles], columns=cols)
        
        # Extract features
        df = TechnicalFeatureExtractor.compute_features(df)
        
        # Extract derivatives features if funding/oi available
        with self.db.get_connection() as conn:
            df_funding = pd.read_sql("SELECT timestamp, funding_rate, mark_price FROM funding_rates WHERE symbol = ?", conn, params=[symbol])
            df_oi = pd.read_sql("SELECT timestamp, open_interest, open_interest_usd FROM open_interest WHERE symbol = ?", conn, params=[symbol])
            
        df = DerivativeFeatureExtractor.compute_features(df, df_funding, df_oi)
        
        decisions = []
        for agent in self.agents:
            dec = agent.evaluate(symbol, timeframe, df)
            if dec['action'] != 'NEUTRAL':
                decisions.append(dec)
                
        return decisions

    def scan_all(self, symbols: List[str], timeframes: List[str] = ["1h", "15m"]) -> List[Dict[str, Any]]:
        all_opportunities = []
        
        for symbol in symbols:
            for tf in timeframes:
                decs = self.process_asset(symbol, tf)
                for dec in decs:
                    approved, reason, trade = self.risk_engine.evaluate_opportunity(dec)
                    entry = {
                        "decision": dec,
                        "approved": approved,
                        "veto_reason": reason,
                        "trade_params": trade
                    }
                    all_opportunities.append(entry)
                    
        # Sort by confidence descending
        all_opportunities.sort(key=lambda x: x["decision"]["confidence"], reverse=True)
        return all_opportunities

if __name__ == "__main__":
    engine = DecisionEngine()
    opportunities = engine.scan_all(['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
    print(f"\nDiscovered {len(opportunities)} opportunities:")
    for opp in opportunities:
        d = opp['decision']
        print(f"\n[{d['agent_name']}] {d['symbol']} ({d['timeframe']}) -> {d['action']} | Conf: {d['confidence']:.2f}")
        print(f"  Approved: {opp['approved']} ({opp['veto_reason']})")
        print(f"  Reasons: {d['reasons']}")
