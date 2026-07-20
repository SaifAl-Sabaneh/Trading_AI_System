"""
HistoryDatabase — Read-mostly research archive (market_history.db)

Completely separate from market_live.db. Never used by live/paper execution.
Every research campaign reads from this database.
"""
import sqlite3
import os
import sys
import time
import hashlib
from typing import List, Tuple, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import HISTORY_DB_PATH, HISTORY_SCHEMA_PATH


class HistoryDatabase:
    def __init__(self, db_path: str = HISTORY_DB_PATH, schema_path: str = HISTORY_SCHEMA_PATH):
        self.db_path = db_path
        self.schema_path = schema_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=-64000;")   # 64 MB cache for large reads
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        if not os.path.exists(self.schema_path):
            raise FileNotFoundError(f"History schema not found: {self.schema_path}")
        with open(self.schema_path, "r") as f:
            schema_sql = f.read()
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    # ------------------------------------------------------------------
    # Insert Methods
    # ------------------------------------------------------------------

    def insert_candles(self, rows: List[Tuple]) -> int:
        """rows: (symbol, timeframe, timestamp, open, high, low, close, volume,
                   quote_volume, taker_buy_volume, taker_buy_quote, trades_count)"""
        if not rows:
            return 0
        q = """
        INSERT OR IGNORE INTO candles_history
            (symbol, timeframe, timestamp, open, high, low, close, volume,
             quote_volume, taker_buy_volume, taker_buy_quote, trades_count)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?);
        """
        with self.get_connection() as conn:
            conn.executemany(q, rows)
            conn.commit()
        return len(rows)

    def insert_funding_rates(self, rows: List[Tuple]) -> int:
        """rows: (symbol, timestamp, funding_rate, mark_price)"""
        if not rows:
            return 0
        q = """
        INSERT OR IGNORE INTO funding_rates_history (symbol, timestamp, funding_rate, mark_price)
        VALUES (?,?,?,?);
        """
        with self.get_connection() as conn:
            conn.executemany(q, rows)
            conn.commit()
        return len(rows)

    def insert_open_interest(self, rows: List[Tuple]) -> int:
        """rows: (symbol, timestamp, open_interest, open_interest_usd)"""
        if not rows:
            return 0
        q = """
        INSERT OR IGNORE INTO open_interest_history (symbol, timestamp, open_interest, open_interest_usd)
        VALUES (?,?,?,?);
        """
        with self.get_connection() as conn:
            conn.executemany(q, rows)
            conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Dataset Metadata
    # ------------------------------------------------------------------

    def record_download(self, dataset_name: str, symbol: str, timeframe: Optional[str],
                        source: str, first_ts: int, last_ts: int, row_count: int,
                        checksum: str = "", notes: str = "") -> None:
        q = """
        INSERT OR REPLACE INTO dataset_metadata
            (dataset_name, symbol, timeframe, source, first_timestamp, last_timestamp,
             row_count, checksum_sha256, download_timestamp, status, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?);
        """
        with self.get_connection() as conn:
            conn.execute(q, (dataset_name, symbol, timeframe, source,
                             first_ts, last_ts, row_count, checksum,
                             int(time.time() * 1000), "complete", notes))
            conn.commit()

    def get_last_downloaded_ts(self, dataset_name: str) -> Optional[int]:
        """Returns the last_timestamp for a given dataset, or None if never downloaded."""
        q = "SELECT MAX(last_timestamp) FROM dataset_metadata WHERE dataset_name = ? AND status = 'complete'"
        with self.get_connection() as conn:
            row = conn.execute(q, (dataset_name,)).fetchone()
        return row[0] if row and row[0] is not None else None

    # ------------------------------------------------------------------
    # Market Regimes
    # ------------------------------------------------------------------

    def seed_market_regimes(self, regimes: List[Dict]) -> int:
        """Seed the market_regimes table. Idempotent (skips existing labels)."""
        q = """
        INSERT OR IGNORE INTO market_regimes
            (regime_label, regime_type, start_timestamp, end_timestamp, description, key_events)
        VALUES (:label, :type, :start, :end, :desc, :events);
        """
        rows = [{"label": r["label"], "type": r["type"],
                 "start": r["start_ms"], "end": r["end_ms"],
                 "desc": r.get("desc", ""), "events": r.get("events", "")}
                for r in regimes]
        with self.get_connection() as conn:
            conn.executemany(q, rows)
            conn.commit()
        return len(rows)

    def fetch_regimes(self) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM market_regimes ORDER BY start_timestamp"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Fetch Methods (used by research campaigns)
    # ------------------------------------------------------------------

    def fetch_candles(self, symbol: str, timeframe: str,
                      start_ts: int = None, end_ts: int = None) -> List[Tuple]:
        q = """SELECT timestamp, open, high, low, close, volume, taker_buy_volume
               FROM candles_history WHERE symbol=? AND timeframe=?"""
        params = [symbol, timeframe]
        if start_ts:
            q += " AND timestamp >= ?"; params.append(start_ts)
        if end_ts:
            q += " AND timestamp <= ?"; params.append(end_ts)
        q += " ORDER BY timestamp ASC"
        with self.get_connection() as conn:
            return conn.execute(q, params).fetchall()

    def fetch_funding_rates(self, symbol: str,
                            start_ts: int = None, end_ts: int = None) -> List[Tuple]:
        q = "SELECT timestamp, funding_rate, mark_price FROM funding_rates_history WHERE symbol=?"
        params = [symbol]
        if start_ts:
            q += " AND timestamp >= ?"; params.append(start_ts)
        if end_ts:
            q += " AND timestamp <= ?"; params.append(end_ts)
        q += " ORDER BY timestamp ASC"
        with self.get_connection() as conn:
            return conn.execute(q, params).fetchall()

    def get_stats(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            candles   = conn.execute("SELECT COUNT(*) FROM candles_history").fetchone()[0]
            funding   = conn.execute("SELECT COUNT(*) FROM funding_rates_history").fetchone()[0]
            oi        = conn.execute("SELECT COUNT(*) FROM open_interest_history").fetchone()[0]
            regimes   = conn.execute("SELECT COUNT(*) FROM market_regimes").fetchone()[0]
            meta      = conn.execute("SELECT COUNT(*) FROM dataset_metadata").fetchone()[0]
            symbols   = conn.execute(
                "SELECT COUNT(DISTINCT symbol) FROM candles_history"
            ).fetchone()[0]
            fr_range  = conn.execute(
                "SELECT MIN(funding_rate), MAX(funding_rate) FROM funding_rates_history"
            ).fetchone()
        return {
            "candles_total": candles,
            "funding_total": funding,
            "oi_total": oi,
            "regimes": regimes,
            "download_batches": meta,
            "symbols": symbols,
            "funding_rate_min": fr_range[0],
            "funding_rate_max": fr_range[1],
        }


if __name__ == "__main__":
    db = HistoryDatabase()
    print("HistoryDatabase initialized.")
    print("Stats:", db.get_stats())
