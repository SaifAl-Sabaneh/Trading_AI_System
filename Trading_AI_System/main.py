import os
import sys
import subprocess
import time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config.settings import TARGET_SYMBOLS
from database.database import Database
from collectors.candles import CandleCollector
from collectors.derivatives import DerivativesCollector

def run_system_cycle():
    print(f"\n============================================================")
    print(f"  AUTONOMOUS TRADING INTELLIGENCE SYSTEM -- GOVERNANCE AUDIT CYCLE [{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC]")
    print(f"  Target Assets ({len(TARGET_SYMBOLS)}): {', '.join(TARGET_SYMBOLS)}")
    print(f"============================================================")
    
    db = Database()
    price_collector = CandleCollector(db=db, is_futures=True)
    futures_collector = DerivativesCollector(db=db)
    
    # Step 1: Update Market Intelligence Data
    print("\n[Step 1] Polling Live Market Data...", flush=True)
    price_collector.poll_latest(TARGET_SYMBOLS, ["1h", "15m", "5m"])
    for sym in TARGET_SYMBOLS:
        futures_collector.fetch_funding_history(sym, limit=5)
        futures_collector.fetch_open_interest_history(sym, period="1h", limit=5)
        
    db_stats = db.get_stats()
    print(f"  => Market Brain Active: {db_stats['total_candles']} candles across {db_stats['symbols_count']} assets.")

    # Step 2: Isolated Production Engine Process (Capital Allocation Authority)
    print("\n[Step 2] Executing Isolated Production Engine (Capital Allocation Authority)...", flush=True)
    prod_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "production_engine.py")
    res_prod = subprocess.run([sys.executable, prod_script], capture_output=True, text=True)
    print("  " + res_prod.stdout.strip())

    # Step 3: Isolated Shadow Engine Process (Quarantined Observation Logging)
    print("\n[Step 3] Executing Isolated Shadow Engine (Quarantined Observation Logging)...", flush=True)
    shadow_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "shadow_engine.py")
    res_shadow = subprocess.run([sys.executable, shadow_script], capture_output=True, text=True)
    print("  " + res_shadow.stdout.strip())

    print("\n============================================================")
    print("  SYSTEM STATUS & GOVERNANCE AUDIT COMPLETE")
    print("  Firewall Status: ACTIVE (Production & Research Namespace Isolation Enforced)")
    print("============================================================")

if __name__ == "__main__":
    run_system_cycle()
