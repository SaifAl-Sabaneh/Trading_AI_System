import time
import os
import sys
from datetime import datetime, timedelta
from typing import List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database
from collectors.binance_client import BinanceClient

class CandleCollector:
    def __init__(self, db: Database = None, is_futures: bool = True):
        self.db = db if db else Database()
        self.client = BinanceClient(is_futures=is_futures)

    def backfill_symbol_timeframe(self, symbol: str, timeframe: str, days_back: int = 14) -> int:
        print(f"Backfilling {timeframe} candles for {symbol} ({days_back} days)...", flush=True)
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=days_back)
        
        current_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)
        
        total_inserted = 0
        
        while current_ts < end_ts:
            params = {
                "symbol": symbol,
                "interval": timeframe,
                "startTime": current_ts,
                "limit": 1000
            }
            batch = self.client.get("/fapi/v1/klines", params=params)
            if not batch:
                break
                
            tuples = [
                (symbol, timeframe, int(item[0]), float(item[1]), float(item[2]), float(item[3]),
                 float(item[4]), float(item[5]), float(item[7]), int(item[8]))
                for item in batch
            ]
            
            self.db.insert_candles(tuples)
            total_inserted += len(tuples)
            
            last_ts = int(batch[-1][0])
            if last_ts <= current_ts:
                break
            current_ts = last_ts + 1
            time.sleep(0.05)
            
        print(f"  => Recorded {total_inserted} {timeframe} candles for {symbol}.", flush=True)
        return total_inserted

    def poll_latest(self, symbols: List[str], timeframes: List[str]) -> int:
        total = 0
        for sym in symbols:
            for tf in timeframes:
                params = {"symbol": sym, "interval": tf, "limit": 5}
                batch = self.client.get("/fapi/v1/klines", params=params)
                if batch:
                    tuples = [
                        (sym, tf, int(item[0]), float(item[1]), float(item[2]), float(item[3]),
                         float(item[4]), float(item[5]), float(item[7]), int(item[8]))
                        for item in batch
                    ]
                    self.db.insert_candles(tuples)
                    total += len(tuples)
        return total

if __name__ == "__main__":
    collector = CandleCollector()
    collector.backfill_symbol_timeframe("BNBUSDT", "1h", days_back=2)
    print("Database Stats:", collector.db.get_stats())
