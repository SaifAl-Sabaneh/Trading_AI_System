import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database.db_manager import DatabaseManager
from collectors.price_collector import PriceCollector
from collectors.futures_collector import FuturesCollector

def main():
    print("============================================================")
    print("  AUTONOMOUS TRADING SYSTEM — PHASE 1 DATA PIPELINE BACKFILL")
    print("============================================================")
    
    db = DatabaseManager()
    price_col = PriceCollector(db_manager=db, is_futures=True)
    futures_col = FuturesCollector(db_manager=db)
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    timeframes = ['1m', '5m', '15m', '1h']
    days_back = 14  # 2 weeks of high-resolution 1m, 5m, 15m, 1h candles
    
    start_time = time.time()
    
    for symbol in symbols:
        print(f"\n>>> PROCESSING ASSET: {symbol}")
        # 1. Price Klines
        for tf in timeframes:
            # Backfill 14 days for 1h/15m/5m/1m
            # Limit days for 1m to 7 days to keep initial DB footprint light & fast
            tf_days = 7 if tf == '1m' else days_back
            price_col.backfill_history(symbol, tf, days_back=tf_days)
            
        # 2. Futures Derivatives (Funding & Open Interest)
        futures_col.fetch_funding_history(symbol, limit=1000)
        futures_col.fetch_open_interest_history(symbol, period="1h", limit=500)
        
    elapsed = time.time() - start_time
    stats = db.get_stats()
    
    print("\n============================================================")
    print("  BACKFILL COMPLETE!")
    print(f"  Elapsed Time: {elapsed:.2f} seconds")
    print("  Database Summary Stats:")
    for k, v in stats.items():
        print(f"    - {k}: {v}")
    print("============================================================")

if __name__ == "__main__":
    main()
