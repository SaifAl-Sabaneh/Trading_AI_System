import urllib.request
import json
import time
import os
import sys
from datetime import datetime, timedelta
from typing import List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import DatabaseManager

class FuturesCollector:
    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager if db_manager else DatabaseManager()
        self.base_url = "https://fapi.binance.com"

    def fetch_funding_history(self, symbol: str, limit: int = 1000) -> int:
        print(f"Fetching funding rates for {symbol}...", flush=True)
        url = f"{self.base_url}/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                
            tuples = []
            for item in data:
                ts = int(item['fundingTime'])
                rate = float(item['fundingRate'])
                mark_price = float(item.get('markPrice', 0.0))
                tuples.append((symbol, ts, rate, mark_price))
                
            inserted = self.db.insert_funding_rates(tuples)
            print(f"  => Recorded {len(tuples)} funding rate entries for {symbol}.", flush=True)
            return len(tuples)
        except Exception as e:
            print(f"Error fetching funding rate for {symbol}: {e}", flush=True)
            return 0

    def fetch_open_interest_history(self, symbol: str, period: str = "1h", limit: int = 500) -> int:
        print(f"Fetching Open Interest history ({period}) for {symbol}...", flush=True)
        url = f"{self.base_url}/futures/data/openInterestHist?symbol={symbol}&period={period}&limit={limit}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                
            tuples = []
            for item in data:
                ts = int(item['timestamp'])
                sum_oi = float(item['sumOpenInterest'])
                sum_oi_val = float(item['sumOpenInterestValue'])
                tuples.append((symbol, ts, sum_oi, sum_oi_val))
                
            inserted = self.db.insert_open_interest(tuples)
            print(f"  => Recorded {len(tuples)} Open Interest entries for {symbol}.", flush=True)
            return len(tuples)
        except Exception as e:
            print(f"Error fetching Open Interest for {symbol}: {e}", flush=True)
            return 0

    def backfill_symbol(self, symbol: str) -> Tuple[int, int]:
        f_count = self.fetch_funding_history(symbol, limit=1000)
        oi_count = self.fetch_open_interest_history(symbol, period="1h", limit=500)
        return f_count, oi_count

if __name__ == "__main__":
    collector = FuturesCollector()
    collector.backfill_symbol("BTCUSDT")
    print("Database Stats:", collector.db.get_stats())
