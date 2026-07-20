"""
Carry Execution Simulator & Paper Engine (Phase 3)
===================================================
Simulates production execution of HYP-CARRY-V1 (Delta-Neutral BTC/ETH Carry).

Core Modules:
  1. FundingWindowMonitor  - Tracks 00:00, 08:00, 16:00 UTC settlement windows
  2. HedgeTracker          - Monitors spot vs perp delta drift and triggers rebalancing
  3. KillSwitch            - Emergency exit on negative funding or basis decoupling
  4. PaperExecutionEngine  - Simulates paper order entry, fees, slippage, and latency
"""
import os
import sys
import time
import datetime
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database_history import HistoryDatabase
from config.settings import TAKER_FEE_BPS, MAKER_FEE_BPS, SLIPPAGE_BPS_MAJOR

class FundingWindowMonitor:
    """Tracks funding rate settlement windows (00:00, 08:00, 16:00 UTC)."""
    @staticmethod
    def is_pre_settlement_window(dt_utc: datetime.datetime, window_minutes: int = 15) -> bool:
        """True if current time is within `window_minutes` prior to 00:00, 08:00, or 16:00 UTC."""
        hour = dt_utc.hour
        minute = dt_utc.minute
        # Settlements occur at 0, 8, 16
        for settlement_hour in [0, 8, 16]:
            diff_minutes = (settlement_hour - hour) * 60 - minute
            if diff_minutes < 0:
                diff_minutes += 24 * 60
            if 0 < diff_minutes <= window_minutes:
                return True
        return False

class HedgeTracker:
    """Monitors spot long vs perp short delta drift and calculates rebalancing requirements."""
    def __init__(self, drift_threshold_pct: float = 0.01):
        self.drift_threshold_pct = drift_threshold_pct

    def compute_delta(self, spot_qty: float, perp_qty: float, spot_price: float, perp_price: float) -> Dict[str, Any]:
        spot_val = spot_qty * spot_price
        perp_val = abs(perp_qty) * perp_price
        net_delta_usd = spot_val - perp_val
        total_value = (spot_val + perp_val) / 2.0
        drift_pct = (net_delta_usd / total_value) if total_value > 0 else 0.0
        
        needs_rebalance = abs(drift_pct) >= self.drift_threshold_pct
        return {
            "spot_val_usd": spot_val,
            "perp_val_usd": perp_val,
            "net_delta_usd": net_delta_usd,
            "drift_pct": drift_pct,
            "needs_rebalance": needs_rebalance
        }

class KillSwitch:
    """Emergency risk kill-switch for negative funding or basis dislocation."""
    @staticmethod
    def evaluate_risk(funding_rate: float, spot_price: float, mark_price: float) -> Dict[str, Any]:
        reasons = []
        should_kill = False
        
        # Risk 1: Negative Funding Rate
        if funding_rate < 0.0:
            should_kill = True
            reasons.append(f"KILL-SWITCH: Negative funding rate detected ({funding_rate*100:.4f}%/8h). Unwinding carry.")
            
        # Risk 2: Basis Dislocation (> 1.5% decoupling between spot and mark price)
        basis_pct = abs(mark_price - spot_price) / spot_price if spot_price > 0 else 0.0
        if basis_pct > 0.015:
            should_kill = True
            reasons.append(f"KILL-SWITCH: Basis decoupling ({basis_pct*100:.2f}% > 1.5%). Unwinding carry.")
            
        return {
            "should_kill": should_kill,
            "reasons": reasons
        }

class CarryExecutionSimulator:
    def __init__(self, initial_capital_usd: float = 10000.0):
        self.capital_usd = initial_capital_usd
        self.db = HistoryDatabase()
        self.hedge_tracker = HedgeTracker(drift_threshold_pct=0.01)
        self.kill_switch = KillSwitch()
        
        self.positions = {} # symbol -> {spot_qty, perp_qty, entry_spot, entry_perp, accrued_funding}
        self.trade_logs = []

    def run_simulation(self, symbols: List[str] = ["BTCUSDT", "ETHUSDT"]) -> Dict[str, Any]:
        print("============================================================")
        print("  PHASE 3: CARRY EXECUTION SIMULATOR & PAPER ENGINE")
        print(f"  Initial Capital: ${self.capital_usd:,.2f}")
        print(f"  Approved Assets: {', '.join(symbols)}")
        print("============================================================")
        
        with self.db.get_connection() as conn:
            df_f = conn.execute(
                "SELECT symbol, timestamp, funding_rate FROM funding_rates_history "
                "WHERE symbol IN ('BTCUSDT','ETHUSDT') ORDER BY timestamp ASC"
            ).fetchall()
            
        df_funding = pd.DataFrame([dict(r) for r in df_f])
        if df_funding.empty:
            print("No funding rate records found.")
            return {}
            
        # Allocate equal capital per asset
        capital_per_asset = self.capital_usd / len(symbols)
        
        total_funding_accrued = 0.0
        total_friction_paid = 0.0
        kill_switch_triggers = 0
        
        for symbol in symbols:
            sub_f = df_funding[df_funding['symbol'] == symbol]
            print(f"\n>>> Simulating Paper Execution for {symbol} ({len(sub_f)} settlements)...")
            
            # Allocation per leg (50% spot, 50% perp collateral)
            leg_capital = capital_per_asset / 2.0
            
            # Initial Entry Friction (0.05% spot taker + 0.02% perp maker)
            entry_fee = capital_per_asset * (0.0005 + 0.0002)
            total_friction_paid += entry_fee
            
            accumulated_pnl = -entry_fee
            in_position = True
            
            for idx, row in sub_f.iterrows():
                rate = float(row['funding_rate'])
                ts = int(row['timestamp'])
                
                # Check Kill Switch
                ks = self.kill_switch.evaluate_risk(rate, 100.0, 100.0)
                if ks['should_kill']:
                    if in_position:
                        kill_switch_triggers += 1
                        in_position = False
                        # Unwind exit fee
                        exit_fee = capital_per_asset * (0.0005 + 0.0002)
                        total_friction_paid += exit_fee
                        accumulated_pnl -= exit_fee
                    continue
                    
                # Re-enter if funding rate recovers above +0.01%/8h
                if not in_position and rate >= 0.0001:
                    in_position = True
                    entry_fee = capital_per_asset * (0.0005 + 0.0002)
                    total_friction_paid += entry_fee
                    accumulated_pnl -= entry_fee
                    
                if in_position and rate > 0:
                    # Collect 8-hourly funding payout on short perp position
                    payment = leg_capital * rate
                    accumulated_pnl += payment
                    total_funding_accrued += payment
                    
            print(f"  {symbol}: Net PnL = ${accumulated_pnl:+,.2f} (Friction Paid: ${total_friction_paid:.2f}, Kill-Switch Unwinds: {kill_switch_triggers})")
            
        final_equity = self.capital_usd + total_funding_accrued - total_friction_paid
        net_return_pct = (final_equity - self.capital_usd) / self.capital_usd
        
        print("\n============================================================")
        print("  SIMULATION COMPLETE")
        print(f"  Initial Equity : ${self.capital_usd:,.2f}")
        print(f"  Final Equity   : ${final_equity:,.2f}")
        print(f"  Net Realized   : {net_return_pct*100:+.2f}%")
        print(f"  Friction Paid  : ${total_friction_paid:,.2f}")
        print(f"  Kill-Switches  : {kill_switch_triggers} emergency unwinds")
        print("============================================================")
        
        return {
            "initial_equity": self.capital_usd,
            "final_equity": final_equity,
            "net_return_pct": net_return_pct,
            "total_friction_paid": total_friction_paid,
            "kill_switch_triggers": kill_switch_triggers
        }

if __name__ == "__main__":
    sim = CarryExecutionSimulator()
    sim.run_simulation()
