import json
import uuid
import time
import os
import sys
from typing import Dict, Any, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import DatabaseManager

class TradeMemoryLogger:
    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager if db_manager else DatabaseManager()

    def log_trade_decision(self, opportunity: Dict[str, Any], current_price: float) -> str:
        trade_id = str(uuid.uuid4())[:8]
        dec = opportunity["decision"]
        trade_params = opportunity.get("trade_params", {})
        
        query = """
        INSERT INTO trade_memory 
        (trade_id, symbol, decision_timestamp, action, confidence, reasons, market_state_snapshot, entry_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        reasons_json = json.dumps(dec.get("reasons", []))
        snapshot_json = json.dumps({
            "agent_name": dec.get("agent_name"),
            "timeframe": dec.get("timeframe"),
            "expected_return_pct": dec.get("expected_return_pct"),
            "expected_risk_pct": dec.get("expected_risk_pct"),
            "allocated_capital_usd": trade_params.get("allocated_capital_usd", 0.0)
        })
        
        now_ts = int(time.time() * 1000)
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (
                trade_id,
                dec["symbol"],
                now_ts,
                dec["action"],
                dec["confidence"],
                reasons_json,
                snapshot_json,
                current_price
            ))
            conn.commit()
            
        print(f"Logged Trade Memory [{trade_id}]: {dec['symbol']} {dec['action']} @ {current_price}", flush=True)
        return trade_id

    def evaluate_matured_trades(self, horizon_bars: int = 24) -> int:
        """
        Evaluates open trade decisions once forward price data has accumulated.
        Computes Realized PnL, MFE %, MAE %, and Decision Quality Score.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT trade_id, symbol, decision_timestamp, action, entry_price FROM trade_memory WHERE evaluated_at IS NULL;")
            unevaluated = cursor.fetchall()
            
            evaluated_count = 0
            now_ts = int(time.time() * 1000)
            
            for trade_id, symbol, dec_ts, action, entry_price in unevaluated:
                if not entry_price or entry_price <= 0:
                    continue
                    
                # Fetch forward candles after decision_timestamp
                forward_candles = self.db.fetch_candles(symbol, "1h", start_ts=dec_ts)
                if len(forward_candles) < horizon_bars:
                    continue  # Wait until 24 bars accumulate
                    
                bars = forward_candles[:horizon_bars]
                highs = [b[2] for b in bars]
                lows = [b[3] for b in bars]
                exit_price = bars[-1][4]
                
                if action in ["BUY", "CARRY_DELTA_NEUTRAL"]:
                    realized_pnl = (exit_price - entry_price) / entry_price
                    mfe = (max(highs) - entry_price) / entry_price
                    mae = (min(lows) - entry_price) / entry_price
                else: # SELL
                    realized_pnl = (entry_price - exit_price) / entry_price
                    mfe = (entry_price - min(lows)) / entry_price
                    mae = (entry_price - max(highs)) / entry_price
                    
                # Decision Quality Score (0 to 100)
                # Rewards positive MFE and positive Realized PnL, penalizes severe MAE
                score = 50.0 + (realized_pnl * 1000.0) + (mfe * 500.0) + (mae * 500.0)
                score = max(0.0, min(100.0, score))
                
                cursor.execute("""
                UPDATE trade_memory 
                SET exit_price = ?, realized_pnl_pct = ?, mfe_pct = ?, mae_pct = ?, decision_quality_score = ?, evaluated_at = ?
                WHERE trade_id = ?;
                """, (exit_price, realized_pnl, mfe, mae, score, now_ts, trade_id))
                evaluated_count += 1
                
            conn.commit()
            return evaluated_count

if __name__ == "__main__":
    logger = TradeMemoryLogger()
    print("TradeMemoryLogger ready.")
