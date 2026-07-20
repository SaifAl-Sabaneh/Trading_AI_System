import sqlite3
import os
import sys
import datetime
from typing import List, Tuple, Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import DB_PATH, SCHEMA_PATH

class Database:
    def __init__(self, db_path: str = DB_PATH, schema_path: str = SCHEMA_PATH):
        self.db_path = db_path
        self.schema_path = schema_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        if not os.path.exists(self.schema_path):
            raise FileNotFoundError(f"Schema file not found at {self.schema_path}")
            
        with open(self.schema_path, "r") as f:
            schema_sql = f.read()
            
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    def insert_candles(self, candles_data: List[Tuple]) -> int:
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

    def insert_liquidations(self, liq_data: List[Tuple]) -> int:
        if not liq_data:
            return 0
        query = """
        INSERT OR REPLACE INTO liquidations (symbol, timestamp, side, quantity, price, usd_value)
        VALUES (?, ?, ?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, liq_data)
            conn.commit()
            return cursor.rowcount

    def insert_market_state(self, state_tuples: List[Tuple]) -> int:
        if not state_tuples:
            return 0
        query = """
        INSERT OR REPLACE INTO market_state (symbol, timeframe, timestamp, trend_state, volatility_state, liquidity_state, risk_state, regime_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, state_tuples)
            conn.commit()
            return cursor.rowcount

    def insert_strategy_statistics(self, stats_tuples: List[Tuple]) -> int:
        if not stats_tuples:
            return 0
        query = """
        INSERT OR REPLACE INTO strategy_statistics 
        (strategy_name, symbol, timeframe, market_state, confidence_bucket, n_decisions, n_executed, win_rate, mean_return_pct, total_return_pct, profit_factor, avg_mfe_pct, avg_mae_pct, calibrated_accuracy, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, stats_tuples)
            conn.commit()
            return cursor.rowcount

    def insert_paper_carry_log(self, log_tuple: Tuple) -> int:
        query = """
        INSERT INTO paper_carry_ledger 
        (timestamp, symbol, spot_price, mark_price, basis_spread_pct, funding_rate_8h, annualized_apr, funding_regime, action, funding_collected_usd, fees_paid_usd, net_pnl_usd, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, log_tuple)
            conn.commit()
            return cursor.rowcount

    def insert_position_event(self, event_tuple: Tuple) -> int:
        query = """
        INSERT INTO paper_position_events
        (timestamp, symbol, event_type, spot_price, mark_price, amount_usd, fee_usd, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, event_tuple)
            conn.commit()
            return cursor.rowcount

    def init_paper_campaign_metadata(self, campaign_id: str, started_at: int, required_end_at: int, min_settlements: int, config_hash: str) -> None:
        query = """
        INSERT OR IGNORE INTO paper_campaign_metadata
        (campaign_id, started_at, required_end_at, min_required_settlements, carry_strategy_hash, status)
        VALUES (?, ?, ?, ?, ?, 'ACTIVE');
        """
        with self.get_connection() as conn:
            conn.execute(query, (campaign_id, started_at, required_end_at, min_settlements, config_hash))
            conn.commit()

    def insert_campaign_event(self, campaign_id: str, event_type: str, details: str, config_hash: str) -> int:
        ts_now = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Fetch previous event's hash to chain cryptographically
            prev_row = cursor.execute(
                "SELECT hash FROM campaign_events WHERE campaign_id = ? ORDER BY event_id DESC LIMIT 1;",
                (campaign_id,)
            ).fetchone()
            prev_hash = prev_row[0] if prev_row else "GENESIS_HASH"
            
            # Compute chained SHA256 digest
            import hashlib
            payload = f"{prev_hash}:{ts_now}:{campaign_id}:{event_type}:{details}:{config_hash}"
            chained_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]
            
            query = """
            INSERT INTO campaign_events (timestamp, campaign_id, event_type, details, hash)
            VALUES (?, ?, ?, ?, ?);
            """
            cursor.execute(query, (ts_now, campaign_id, event_type, details, chained_hash))
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
            candles_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM funding_rates;")
            funding_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM open_interest;")
            oi_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM liquidations;")
            liq_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM market_state;")
            state_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM trade_memory;")
            memory_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM strategy_statistics;")
            stats_cnt = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT symbol), COUNT(DISTINCT timeframe) FROM candles;")
            sym_cnt, tf_cnt = cursor.fetchone()
            
            return {
                "total_candles": candles_cnt,
                "total_funding": funding_cnt,
                "total_open_interest": oi_cnt,
                "total_liquidations": liq_cnt,
                "total_market_states": state_cnt,
                "total_trade_memories": memory_cnt,
                "total_strategy_stats": stats_cnt,
                "symbols_count": sym_cnt,
                "timeframes_count": tf_cnt
            }

if __name__ == "__main__":
    db = Database()
    print("Database schema re-initialized successfully.")
    print("Stats:", db.get_stats())
