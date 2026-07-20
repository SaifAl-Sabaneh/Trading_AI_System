import sqlite3
import os
from typing import List, Tuple, Dict, Any

class DatabaseManager:
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "market.db")
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Candles table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                quote_volume REAL DEFAULT 0.0,
                trades_count INTEGER DEFAULT 0,
                PRIMARY KEY (symbol, timeframe, timestamp)
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol, timeframe, timestamp);")

            # 2. Funding Rates table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS funding_rates (
                symbol TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                funding_rate REAL NOT NULL,
                mark_price REAL DEFAULT 0.0,
                PRIMARY KEY (symbol, timestamp)
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_funding_lookup ON funding_rates(symbol, timestamp);")

            # 3. Open Interest table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS open_interest (
                symbol TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open_interest REAL NOT NULL,
                open_interest_usd REAL DEFAULT 0.0,
                PRIMARY KEY (symbol, timestamp)
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_oi_lookup ON open_interest(symbol, timestamp);")

            # 4. Trade Memory table (for Phase 4/5)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_memory (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                decision_timestamp INTEGER NOT NULL,
                action TEXT NOT NULL,
                confidence REAL NOT NULL,
                reasons TEXT NOT NULL,
                market_state_snapshot TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                realized_pnl_pct REAL,
                mfe_pct REAL,
                mae_pct REAL,
                decision_quality_score REAL,
                evaluated_at INTEGER
            );
            """)
            conn.commit()

    def insert_candles(self, candles_data: List[Tuple]) -> int:
        """
        candles_data: List of tuples (symbol, timeframe, timestamp, open, high, low, close, volume, quote_volume, trades_count)
        """
        if not candles_data:
            return 0
        query = """
        INSERT OR REPLACE INTO candles 
        (symbol, timeframe, timestamp, open, high, low, close, volume, quote_volume, trades_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, candles_data)
            conn.commit()
            return cursor.rowcount

    def insert_funding_rates(self, funding_data: List[Tuple]) -> int:
        """
        funding_data: List of tuples (symbol, timestamp, funding_rate, mark_price)
        """
        if not funding_data:
            return 0
        query = """
        INSERT OR REPLACE INTO funding_rates (symbol, timestamp, funding_rate, mark_price)
        VALUES (?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, funding_data)
            conn.commit()
            return cursor.rowcount

    def insert_open_interest(self, oi_data: List[Tuple]) -> int:
        """
        oi_data: List of tuples (symbol, timestamp, open_interest, open_interest_usd)
        """
        if not oi_data:
            return 0
        query = """
        INSERT OR REPLACE INTO open_interest (symbol, timestamp, open_interest, open_interest_usd)
        VALUES (?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, oi_data)
            conn.commit()
            return cursor.rowcount

    def fetch_candles(self, symbol: str, timeframe: str, start_ts: int = None, end_ts: int = None) -> List[Tuple]:
        query = "SELECT timestamp, open, high, low, close, volume FROM candles WHERE symbol = ? AND timeframe = ?"
        params = [symbol, timeframe]
        if start_ts is not None:
            query += " AND timestamp >= ?"
            params.append(start_ts)
        if end_ts is not None:
            query += " AND timestamp <= ?"
            params.append(end_ts)
        query += " ORDER BY timestamp ASC"
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def get_stats(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM candles;")
            candles_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM funding_rates;")
            funding_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM open_interest;")
            oi_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT symbol), COUNT(DISTINCT timeframe) FROM candles;")
            symbols_count, timeframes_count = cursor.fetchone()
            
            return {
                "total_candles": candles_count,
                "total_funding_rows": funding_count,
                "total_oi_rows": oi_count,
                "symbols_count": symbols_count,
                "timeframes_count": timeframes_count
            }

if __name__ == "__main__":
    db = DatabaseManager()
    print("Database initialized successfully.")
    print("Stats:", db.get_stats())
