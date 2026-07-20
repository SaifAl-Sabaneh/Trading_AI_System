"""
24/7 Continuous Background Observer Daemon (engine/run_247_observer.py)
========================================================================
Runs continuous polling cycles every N seconds (default: 300s / 5 mins),
persisting live spot/perp prices, basis spreads, funding payouts, and chained audit logs
to database/market_live.db.

Features:
  - Top-level exception recovery (network outages will not crash the loop)
  - Automatic database backups via OperationalWatchdog
  - Hourly health heartbeat output
"""

import os
import sys
import time
import datetime
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.live_paper_observer import LivePaperObserver
from engine.operational_watchdog import OperationalWatchdog

def run_247_loop(poll_interval_seconds: int = 300):
    print("=" * 80)
    print("  STARTING 24/7 CONTINUOUS LIVE PAPER OBSERVER DAEMON")
    print(f"  Poll Interval : Every {poll_interval_seconds} seconds ({poll_interval_seconds/60:.1f} mins)")
    print(f"  Campaign ID   : CARRY-PAPER-V1-20260720")
    print(f"  Config Hash   : SHA256[3965622973c9fdc2]")
    print("=" * 80)

    observer = LivePaperObserver()
    watchdog = OperationalWatchdog()
    cycle_count = 0

    while True:
        cycle_count += 1
        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"\n[LOOP CYCLE #{cycle_count}] {now_utc}")
        
        try:
            # 1. Execute live observation cycle
            observer.run_observation_cycle()
        except Exception as e:
            print(f"  [ERROR] Transient observation error: {e}")
            traceback.print_exc()

        # 2. Run operational watchdog audit every 12 cycles (~1 hour)
        if cycle_count % 12 == 0 or cycle_count == 1:
            try:
                wd_report = watchdog.run_full_health_audit()
                print(f"  [WATCHDOG HEALTH] {wd_report['overall_health']} | Backup: {wd_report['backup_status']} | Gaps: {wd_report['data_gap_status']}")
            except Exception as ex:
                print(f"  [WATCHDOG ERROR] {ex}")

        # 3. Wait for next poll interval
        time.sleep(poll_interval_seconds)

if __name__ == "__main__":
    # Default: Poll every 5 minutes (300 seconds)
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    run_247_loop(poll_interval_seconds=interval)
