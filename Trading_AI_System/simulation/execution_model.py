import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import TAKER_FEE_BPS, MAKER_FEE_BPS, SLIPPAGE_BPS_MAJOR, SLIPPAGE_BPS_ALT

class ExecutionModel:
    @staticmethod
    def calculate_execution(symbol: str, signal_price: float, action: str, is_taker: bool = True) -> dict:
        """
        Calculates realistic entry/exit price after fees and market slippage.
        """
        fee_bps = TAKER_FEE_BPS if is_taker else MAKER_FEE_BPS
        slippage_bps = SLIPPAGE_BPS_MAJOR if symbol in ["BTCUSDT", "ETHUSDT"] else SLIPPAGE_BPS_ALT
        
        total_friction_bps = fee_bps + slippage_bps
        friction_factor = total_friction_bps / 10000.0
        
        if action in ["BUY", "CARRY_DELTA_NEUTRAL"]:
            executed_price = signal_price * (1.0 + friction_factor)
        else: # SELL
            executed_price = signal_price * (1.0 - friction_factor)
            
        return {
            "symbol": symbol,
            "action": action,
            "signal_price": signal_price,
            "executed_price": executed_price,
            "fee_bps": fee_bps,
            "slippage_bps": slippage_bps,
            "total_friction_pct": friction_factor * 100.0
        }

if __name__ == "__main__":
    ex = ExecutionModel.calculate_execution("SOLUSDT", 150.0, "BUY")
    print("Execution Simulation Result:", ex)
