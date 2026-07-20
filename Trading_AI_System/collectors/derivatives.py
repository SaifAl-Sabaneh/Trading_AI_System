import time
import os
import sys
from typing import List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database
from collectors.binance_client import BinanceClient

class DerivativesCollector:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()
        self.client = BinanceClient(is_futures=True)

    def fetch_funding_history(self, symbol: str, limit: int = 1000) -> int:
        params = {"symbol": symbol, "limit": limit}
        data = self.client.get("/fapi/v1/fundingRate", params=params)
        if not data:
            return 0
            
        tuples = [
            (symbol, int(item['fundingTime']), float(item['fundingRate']), float(item.get('markPrice', 0.0)))
            for item in data
        ]
        self.db.insert_funding_rates(tuples)
        print(f"  => Recorded {len(tuples)} funding rate entries for {symbol}.", flush=True)
        return len(tuples)

    def fetch_open_interest_history(self, symbol: str, period: str = "1h", limit: int = 500) -> int:
        params = {"symbol": symbol, "period": period, "limit": limit}
        data = self.client.get("/futures/data/openInterestHist", params=params)
        if not data:
            return 0
            
        tuples = [
            (symbol, int(item['timestamp']), float(item['sumOpenInterest']), float(item['sumOpenInterestValue']))
            for item in data
        ]
        self.db.insert_open_interest(tuples)
        print(f"  => Recorded {len(tuples)} Open Interest entries for {symbol}.", flush=True)
        return len(tuples)

if __name__ == "__main__":
    collector = DerivativesCollector()
    collector.fetch_funding_history("BNBUSDT", limit=100)
    print("Database Stats:", collector.db.get_stats())
