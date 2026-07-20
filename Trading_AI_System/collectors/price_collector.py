import urllib.request
import json
import time
import os
import sys
from datetime import datetime, timedelta
from typing import List, Tuple

# Add parent directory to path so we can import database.db_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import DatabaseManager

class PriceCollector:
    def __init__(self, db_manager: DatabaseManager = None, is_futures: bool = True):
        self.db = db_manager if db_manager else DatabaseManager()
        self.is_futures = is_futures
        self.base_url = "https://fapi.binance.com/fapi/v1/klines" if is_futures else "https://api.binance.com/api/v3/klines"

    def fetch_klines_batch(self, symbol: str, interval: str, start_time: int = None, limit: int = 1000) -> List:
        url = f"{self.base_url}?symbol={symbol}&interval={interval}&limit={limit}"
        if start_time:
            url += f"&startTime={start_time}"
            
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data
        except Exception as e:
            print(f"Error fetching klines batch ({symbol}, {interval}): {e}", flush=True)
            return []

    def backfill_history(self, symbol: str, interval: str, days_back: int = 30) -> int:
        print(f"Backfilling {interval} candles for {symbol} ({days_back} days)...", flush=True)
        end_time_dt = datetime.utcnow()
        start_time_dt = end_time_dt - timedelta(days=days_back)
        
        current_ts = int(start_time_dt.timestamp() * 1000)
        end_ts = int(end_time_dt.timestamp() * 1000)
        
        total_inserted = 0
        
        while current_ts < end_ts:
            batch = self.fetch_klines_batch(symbol, interval, start_time=current_ts, limit=1000)
            if not batch:
                break
                
            candles_tuples = []
            for item in batch:
                open_time = int(item[0])
                open_p = float(item[1])
                high_p = float(item[2])
                low_p = float(item[3])
                close_p = float(item[4])
                vol = float(item[5])
                qvol = float(item[7])
                trades = int(item[8])
                candles_tuples.append((symbol, interval, open_time, open_p, high_p, low_p, close_p, vol, qvol, trades))
                
            inserted = self.db.insert_candles(candles_tuples)
            total_inserted += len(candles_tuples)
            
            last_candle_ts = int(batch[-1][0])
            if last_candle_ts <= current_ts:
                break
            current_ts = last_candle_ts + 1
            
            # Respect rate limit gently
            time.sleep(0.1)
            
        print(f"  => Finished {symbol} {interval}: {total_inserted} candles recorded.", flush=True)
        return total_inserted

    def poll_latest(self, symbols: List[str], intervals: List[str]) -> int:
        total_new = 0
        for symbol in symbols:
            for interval in intervals:
                batch = self.fetch_klines_batch(symbol, interval, limit=5)
                if batch:
                    tuples = [
                        (symbol, interval, int(item[0]), float(item[1]), float(item[2]), float(item[3]),
                         float(item[4]), float(item[5]), float(item[7]), int(item[8]))
                        for item in batch
                    ]
                    inserted = self.db.insert_candles(tuples)
                    total_new += len(tuples)
        return total_new

if __name__ == "__main__":
    collector = PriceCollector()
    # Quick test: backfill 1 day of 1h candles for BTCUSDT
    collector.backfill_history("BTCUSDT", "1h", days_back=2)
    db_stats = collector.db.get_stats()
    print("Database Stats after backfill:", db_stats)
