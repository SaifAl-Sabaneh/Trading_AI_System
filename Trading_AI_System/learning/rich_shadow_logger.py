import os
import sys
import json
import uuid
import time
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database

class RichShadowLogger:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()

    def log_shadow_prediction(self, observation: Dict[str, Any], current_price: float) -> str:
        trade_id = str(uuid.uuid4())[:8]
        symbol = observation["symbol"]
        timeframe = observation.get("timeframe", "1h")
        action = observation["action"]
        confidence = observation["confidence"]
        agent_name = observation["agent_name"]
        
        # Determine Information Edge type & Gate 0 status
        if agent_name == "CarryAgent":
            info_edge = "FUNDING_DERIVATIVES"
            econ_reason = "Perpetual funding rate imbalance between longs and shorts"
        elif agent_name == "LiquidationAgent":
            info_edge = "FORCE_ORDER_LIQUIDATIONS"
            econ_reason = "Exchange liquidation engine forced sell-off exhaustion"
        else:
            info_edge = "TECHNICAL_INDICATOR"
            econ_reason = "Unconstrained price pattern / lagging indicator"

        snapshot = {
            "agent_name": agent_name,
            "tier": "RESEARCH",
            "info_edge_type": info_edge,
            "economic_constraint_reason": econ_reason,
            "predicted_confidence": confidence,
            "predicted_mfe_target": observation.get("expected_return_pct", 0.025),
            "predicted_mae_invalidation": observation.get("expected_risk_pct", 0.012),
            "timeframe": timeframe
        }
        
        now_ts = int(time.time() * 1000)
        reasons_json = json.dumps(observation.get("reasons", []))
        snapshot_json = json.dumps(snapshot)
        
        query = """
        INSERT OR REPLACE INTO trade_memory 
        (trade_id, symbol, timeframe, decision_timestamp, action, confidence, tier, reasons, market_state_snapshot, entry_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (
                trade_id, symbol, timeframe, now_ts, action, confidence, "RESEARCH", reasons_json, snapshot_json, current_price
            ))
            conn.commit()
            
        print(f"Rich Shadow Prediction Logged [{trade_id}]: {agent_name} {symbol} {action} ({info_edge}) @ {current_price}", flush=True)
        return trade_id

if __name__ == "__main__":
    logger = RichShadowLogger()
    sample_obs = {"symbol": "BTCUSDT", "timeframe": "1h", "action": "BUY", "confidence": 0.75, "agent_name": "LiquidationAgent", "reasons": ["OI Flush"]}
    logger.log_shadow_prediction(sample_obs, 105000.0)
