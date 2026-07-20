import time
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config.settings import TARGET_SYMBOLS, TIMEFRAMES
from database.database import Database
from collectors.candles import CandleCollector
from collectors.derivatives import DerivativesCollector
from collectors.liquidation import LiquidationCollector

def main():
    print("============================================================")
    print("  AUTONOMOUS TRADING SYSTEM -- MASTER MARKET BRAIN BACKFILL")
    print(f"  Target Assets ({len(TARGET_SYMBOLS)}): {', '.join(TARGET_SYMBOLS)}")
    print(f"  Timeframes ({len(TIMEFRAMES)}): {', '.join(TIMEFRAMES)}")
    print("============================================================")
    
    db = Database()
    candle_col = CandleCollector(db=db)
    deriv_col = DerivativesCollector(db=db)
    liq_col = LiquidationCollector(db=db)
    
    start_time = time.time()
    
    for symbol in TARGET_SYMBOLS:
        print(f"\n>>> PROCESSING ASSET: {symbol}", flush=True)
        # 1. Candles
        for tf in TIMEFRAMES:
            # Keep 1m days to 7, others to 14 days for fast initial setup
            days = 7 if tf == '1m' else 14
            candle_col.backfill_symbol_timeframe(symbol, tf, days_back=days)
            
        # 2. Derivatives
        deriv_col.fetch_funding_history(symbol, limit=1000)
        deriv_col.fetch_open_interest_history(symbol, period="1h", limit=500)
        
        # 3. Liquidations
        liq_col.fetch_recent_liquidations(symbol, limit=100)
        
    elapsed = time.time() - start_time
    stats = db.get_stats()
    
    print("\n============================================================")
    print("  MASTER BACKFILL COMPLETE!")
    print(f"  Elapsed Time: {elapsed:.2f} seconds")
    print("  Database Summary Stats:")
    for k, v in stats.items():
        print(f"    - {k}: {v}")
    print("============================================================")

if __name__ == "__main__":
    main()
