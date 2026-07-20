import os
import sys
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simulation.execution_model import ExecutionModel
from simulation.portfolio import Portfolio

class Simulator:
    def __init__(self, portfolio: Portfolio = None):
        self.portfolio = portfolio if portfolio else Portfolio()

    def simulate_trade(self, opportunity: Dict[str, Any], signal_price: float) -> dict:
        dec = opportunity["decision"]
        trade_params = opportunity.get("trade_params", {})
        symbol = dec["symbol"]
        action = dec["action"]
        capital = trade_params.get("allocated_capital_usd", 20.0)
        
        exec_info = ExecutionModel.calculate_execution(symbol, signal_price, action)
        exec_price = exec_info["executed_price"]
        
        position = {
            "symbol": symbol,
            "action": action,
            "signal_price": signal_price,
            "entry_price": exec_price,
            "capital_usd": capital,
            "units": capital / exec_price if exec_price > 0 else 0.0,
            "friction_pct": exec_info["total_friction_pct"]
        }
        
        self.portfolio.active_positions[symbol] = position
        return position

if __name__ == "__main__":
    sim = Simulator()
    test_opp = {
        "decision": {"symbol": "BTCUSDT", "action": "BUY", "confidence": 0.70},
        "trade_params": {"allocated_capital_usd": 20.0}
    }
    pos = sim.simulate_trade(test_opp, 105000.0)
    print("Simulated Position:", pos)
    print("Portfolio State:", sim.portfolio.get_summary())
