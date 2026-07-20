import os
import sys
import pandas as pd
from typing import List, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database_history import HistoryDatabase
from database.database import Database
from features.technical_features import TechnicalFeatureExtractor
from features.derivative_features import DerivativeFeatureExtractor

# STRICT IMPORT FIREWALL: Import ONLY from strategies.production
from strategies.production import CarryAgent

class ProductionEngine:
    """
    Production Execution Engine (Strict Code Quarantine)
    
    Enforces a physical import firewall at runtime.
    Processes only validated production agents (CarryAgent) on approved major caps.
    """
    def __init__(self, use_history_db: bool = True):
        self.use_history_db = use_history_db
        if use_history_db:
            self.db = HistoryDatabase()
        else:
            self.db = Database()
            
        # Enforce Firewall check
        self._verify_import_firewall()
        self.production_agents = [
            CarryAgent() # Only CarryAgent is allowed production capital authority
        ]

    def _verify_import_firewall(self):
        """
        Enforces a hard runtime check: if any unvalidated research strategy module is loaded into memory,
        raise a fatal ImportError immediately to prevent accidental strategy creep.
        """
        forbidden_modules = [
            "strategies.research.momentum",
            "strategies.research.mean_reversion",
            "strategies.research.liquidation",
            "strategies.research.funding_reversion"
        ]
        for mod in forbidden_modules:
            if mod in sys.modules:
                raise ImportError(f"CRITICAL FIREWALL VIOLATION: Quarantined research module '{mod}' loaded into ProductionEngine!")

    def process_production_symbols(self, symbols: List[str] = ["BTCUSDT", "ETHUSDT"]) -> List[Dict[str, Any]]:
        approved_signals = []
        
        with self.db.get_connection() as conn:
            if self.use_history_db:
                df_funding_all = pd.read_sql("SELECT symbol, timestamp, funding_rate, mark_price FROM funding_rates_history;", conn)
                df_oi_all = pd.read_sql("SELECT symbol, timestamp, open_interest, open_interest_usd FROM open_interest_history;", conn)
            else:
                df_funding_all = pd.read_sql("SELECT symbol, timestamp, funding_rate, mark_price FROM funding_rates;", conn)
                df_oi_all = pd.read_sql("SELECT symbol, timestamp, open_interest, open_interest_usd FROM open_interest;", conn)

        for symbol in symbols:
            candles = self.db.fetch_candles(symbol, "1h")
            if not candles:
                continue
            cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df = pd.DataFrame([c[:6] for c in candles], columns=cols)
            df = TechnicalFeatureExtractor.compute_features(df)
            
            df_funding = df_funding_all[df_funding_all['symbol'] == symbol]
            df_oi = df_oi_all[df_oi_all['symbol'] == symbol]
            
            df = DerivativeFeatureExtractor.compute_features(df, df_funding, df_oi)
            
            for agent in self.production_agents:
                dec = agent.evaluate(symbol, "1h", df)
                if dec["action"] != "NEUTRAL":
                    approved_signals.append(dec)
                    
        return approved_signals

if __name__ == "__main__":
    engine = ProductionEngine()
    print("ProductionEngine loaded successfully under strict Code Quarantine.")
    print("Production Active Agents:", [a.name for a in engine.production_agents])
    sigs = engine.process_production_symbols(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    print(f"Approved Production Allocation Signals ({len(sigs)}):")
    for s in sigs:
        print(f"  [{s['action']}] {s['symbol']} - Conf: {s['confidence']*100:.0f}%, ExpRet: {s['expected_return_pct']*100:.3f}%/day")
        print("   Reasons:", s['reasons'])
