import os
import sys
import time
import json
import uuid
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import TARGET_SYMBOLS
from database.database import Database
from features.technical_features import TechnicalFeatureExtractor
from features.derivative_features import DerivativeFeatureExtractor
from features.market_state import MarketStateClassifier
from strategies.production.carry import CarryAgent
from strategies.research.momentum import MomentumAgent
from strategies.research.mean_reversion import MeanReversionAgent
from strategies.research.liquidation import LiquidationAgent
from decision.trade_manager import TradeManager
from learning.evaluator import Evaluator

class ManagedDecisionSimulator:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()
        self.trade_manager = TradeManager()
        self.agents = [
            CarryAgent(),
            MomentumAgent(),
            MeanReversionAgent(),
            LiquidationAgent()
        ]
        self.evaluator = Evaluator(db=self.db)

    def run_managed_simulation(self, symbols=TARGET_SYMBOLS, timeframe="1h", max_bars=500) -> int:
        print("============================================================")
        print("  TRADE MANAGEMENT INTELLIGENCE SIMULATOR -- DYNAMIC EXITS")
        print(f"  Target Assets ({len(symbols)}): {', '.join(symbols)}")
        print(f"  Timeframe: {timeframe} | Max Bars per Asset: {max_bars}")
        print("============================================================")
        
        start_time = time.time()
        total_decisions = 0
        
        # Reset memory tables for fresh simulation
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM trade_memory;")
            conn.execute("DELETE FROM strategy_statistics;")
            conn.commit()
            
            df_funding_all = pd.read_sql("SELECT symbol, timestamp, funding_rate, mark_price FROM funding_rates;", conn)
            df_oi_all = pd.read_sql("SELECT symbol, timestamp, open_interest, open_interest_usd FROM open_interest;", conn)

        for symbol in symbols:
            print(f"\n>>> Simulating Managed Decisions for {symbol} ({timeframe})...", flush=True)
            candles = self.db.fetch_candles(symbol, timeframe)
            if not candles or len(candles) < 100:
                print(f"  Skip {symbol}: insufficient candles.", flush=True)
                continue
                
            cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df_full = pd.DataFrame([c[:6] for c in candles], columns=cols)
            
            df_funding = df_funding_all[df_funding_all['symbol'] == symbol]
            df_oi = df_oi_all[df_oi_all['symbol'] == symbol]
            
            df_full = TechnicalFeatureExtractor.compute_features(df_full)
            df_full = DerivativeFeatureExtractor.compute_features(df_full, df_funding, df_oi)
            
            max_idx = min(len(df_full) - 25, max_bars)
            symbol_decisions = []
            
            for i in range(50, max_idx, 1):
                df_window = df_full.iloc[:i+1]
                latest_bar = df_window.iloc[-1]
                dec_ts = int(latest_bar['timestamp'])
                entry_price = float(latest_bar['close'])
                
                trend_st, vol_st, liq_st, risk_st, regime_sc = MarketStateClassifier.classify(df_window)
                
                for agent in self.agents:
                    dec = agent.evaluate(symbol, timeframe, df_window)
                    trade_id = str(uuid.uuid4())[:8]
                    
                    # Construct managed trade plan
                    trade_plan = self.trade_manager.build_trade_plan({"decision": dec}, entry_price)
                    
                    reasons_json = json.dumps(dec.get("reasons", []))
                    snapshot_json = json.dumps({
                        "agent_name": agent.name,
                        "tier": getattr(agent, "tier", "RESEARCH"),
                        "timeframe": timeframe,
                        "regime": vol_st,
                        "tp1_price": trade_plan["tp1_price"],
                        "invalidation_stop_price": trade_plan["invalidation_stop_price"],
                        "allocated_capital_usd": trade_plan["allocated_capital_usd"]
                    })
                    
                    symbol_decisions.append((
                        trade_id,
                        symbol,
                        timeframe,
                        dec_ts,
                        dec["action"],
                        dec["confidence"],
                        getattr(agent, "tier", "RESEARCH"),
                        reasons_json,
                        snapshot_json,
                        entry_price
                    ))
                    
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany("""
                INSERT OR REPLACE INTO trade_memory 
                (trade_id, symbol, timeframe, decision_timestamp, action, confidence, tier, reasons, market_state_snapshot, entry_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, symbol_decisions)
                conn.commit()
                
            total_decisions += len(symbol_decisions)
            print(f"  => Recorded {len(symbol_decisions)} managed decision memories for {symbol}.", flush=True)

        elapsed = time.time() - start_time
        print(f"\n============================================================")
        print(f"  MANAGED SIMULATION COMPLETE: Recorded {total_decisions} memories in {elapsed:.2f}s.")
        print("  Evaluating forward outcomes and generating trade management report...")
        print("============================================================")
        
        report = self.evaluator.generate_strategy_calibration_report()
        return total_decisions

if __name__ == "__main__":
    sim = ManagedDecisionSimulator()
    sim.run_managed_simulation(max_bars=500)
