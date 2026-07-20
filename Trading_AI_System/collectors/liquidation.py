import time
import os
import sys
from typing import List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database
from collectors.binance_client import BinanceClient

class LiquidationCollector:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()
        self.client = BinanceClient(is_futures=True)

    def fetch_recent_liquidations(self, symbol: str, limit: int = 100) -> int:
        # Fetch force orders with limit
        params = {"symbol": symbol, "limit": limit}
        try:
            data = self.client.get("/fapi/v1/allForceOrders", params=params)
            if not data or not isinstance(data, list):
                return 0
                
            tuples = []
            for item in data:
                ts = int(item['time'])
                side = item['side']
                qty = float(item['executedQty'])
                price = float(item['averagePrice'])
                usd_val = qty * price
                tuples.append((symbol, ts, side, qty, price, usd_val))
                
            self.db.insert_liquidations(tuples)
            print(f"  => Recorded {len(tuples)} recent liquidation orders for {symbol}.", flush=True)
            return len(tuples)
        except Exception as e:
            # Silence expected API permission error for force orders
            return 0

if __name__ == "__main__":
    collector = LiquidationCollector()
    collector.fetch_recent_liquidations("BTCUSDT")
    print("Database Stats:", collector.db.get_stats())
