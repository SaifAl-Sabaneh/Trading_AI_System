import os
import sys
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning.exit_optimizer import ExitOptimizer
from learning.position_sizer import PositionSizer

class TradeManager:
    def __init__(self):
        self.exit_optimizer = ExitOptimizer()

    def build_trade_plan(self, opportunity: Dict[str, Any], current_price: float, account_balance: float = 200.0) -> Dict[str, Any]:
        dec = opportunity["decision"]
        symbol = dec["symbol"]
        action = dec["action"]
        agent_name = dec["agent_name"]
        
        # 1. Derive optimal exit parameters for this strategy and asset
        exit_rules = self.exit_optimizer.derive_optimal_exit_rules(agent_name, symbol)
        
        tp1_target_pct = exit_rules["tp1_target_pct"]
        invalidation_stop_pct = exit_rules["invalidation_stop_pct"]
        
        # Calculate concrete price levels
        if action in ["BUY", "CARRY_DELTA_NEUTRAL"]:
            tp1_price = current_price * (1.0 + tp1_target_pct)
            invalidation_stop_price = current_price * (1.0 - invalidation_stop_pct)
            breakeven_trigger_price = tp1_price
        else: # SELL
            tp1_price = current_price * (1.0 - tp1_target_pct)
            invalidation_stop_price = current_price * (1.0 + invalidation_stop_pct)
            breakeven_trigger_price = tp1_price
            
        # 2. Dynamic Position Sizing
        allocated_capital_usd = PositionSizer.calculate_position_size(
            win_rate=dec.get("confidence", 0.60),
            avg_win_pct=dec.get("expected_return_pct", 0.025),
            avg_loss_pct=dec.get("expected_risk_pct", 0.012),
            account_balance=account_balance
        )
        
        return {
            "symbol": symbol,
            "agent_name": agent_name,
            "action": action,
            "confidence": dec["confidence"],
            "entry_price": current_price,
            "tp1_price": tp1_price,
            "tp1_ratio": 0.50,
            "breakeven_trigger_price": breakeven_trigger_price,
            "invalidation_stop_price": invalidation_stop_price,
            "allocated_capital_usd": allocated_capital_usd,
            "reasons": dec.get("reasons", [])
        }

if __name__ == "__main__":
    tm = TradeManager()
    opp = {"decision": {"symbol": "AVAXUSDT", "agent_name": "MomentumAgent", "action": "SELL", "confidence": 0.65, "expected_return_pct": 0.025, "expected_risk_pct": 0.012}}
    plan = tm.build_trade_plan(opp, 6.436)
    print("Structured Trade Plan:")
    print(plan)
