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
        base_dir = os.path.dirname(self.db_path)
        self.ledger_csv = os.path.join(base_dir, "paper_carry_ledger.csv")
        self.events_csv = os.path.join(base_dir, "campaign_events.csv")
        os.makedirs(base_dir, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=DELETE;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            return conn
        except sqlite3.DatabaseError as e:
            print(f"[WARN] SQLite DatabaseError encountered ({e}). Recreating database file...")
            if os.path.exists(self.db_path):
                try:
                    os.remove(self.db_path)
                except Exception:
                    pass
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=DELETE;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            if os.path.exists(self.schema_path):
                with open(self.schema_path, "r") as f:
                    conn.executescript(f.read())
            return conn

    def _init_db(self):
        if not os.path.exists(self.schema_path):
            raise FileNotFoundError(f"Schema file not found at {self.schema_path}")
            
        with open(self.schema_path, "r") as f:
            schema_sql = f.read()
            
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()
            
        self._sync_csv_to_sqlite()

    def _sync_csv_to_sqlite(self):
        import csv
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Sync paper_carry_ledger.csv into SQLite table if CSV exists
            if os.path.exists(self.ledger_csv):
                try:
                    with open(self.ledger_csv, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for r in reader:
                            if float(r.get('spot_price', 0) or 0) > 0 and float(r.get('mark_price', 0) or 0) > 0:
                                cursor.execute("""
                                INSERT OR IGNORE INTO paper_carry_ledger
                                (timestamp, symbol, spot_price, mark_price, basis_spread_pct, funding_rate_8h, annualized_apr, funding_regime, action, funding_collected_usd, fees_paid_usd, net_pnl_usd, status)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                                """, (
                                    int(r['timestamp']), r['symbol'], float(r['spot_price']), float(r['mark_price']),
                                    float(r['basis_spread_pct']), float(r['funding_rate_8h']), float(r['annualized_apr']),
                                    r['funding_regime'], r['action'], float(r['funding_collected_usd']),
                                    float(r['fees_paid_usd']), float(r['net_pnl_usd']), r['status']
                                ))
                except Exception as ex:
                    print(f"  [WARN] Failed to sync ledger CSV to SQLite: {ex}")

            # Sync campaign_events.csv into SQLite table if CSV exists
            if os.path.exists(self.events_csv):
                try:
                    with open(self.events_csv, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for r in reader:
                            cursor.execute("""
                            INSERT OR IGNORE INTO campaign_events
                            (timestamp, campaign_id, event_type, details, hash)
                            VALUES (?, ?, ?, ?, ?);
                            """, (
                                int(r['timestamp']), r['campaign_id'], r['event_type'], r['details'], r['hash']
                            ))
                except Exception as ex:
                    print(f"  [WARN] Failed to sync events CSV to SQLite: {ex}")
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
        import csv
        # 1. Write to CSV first for 100% data preservation
        try:
            file_exists = os.path.exists(self.ledger_csv)
            with open(self.ledger_csv, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'symbol', 'spot_price', 'mark_price', 'basis_spread_pct', 'funding_rate_8h', 'annualized_apr', 'funding_regime', 'action', 'funding_collected_usd', 'fees_paid_usd', 'net_pnl_usd', 'status'])
                writer.writerow(list(log_tuple))
        except Exception as ex:
            print(f"  [WARN] Failed to write ledger row to CSV: {ex}")

        # 2. Insert into SQLite table
        query = """
        INSERT INTO paper_carry_ledger 
        (timestamp, symbol, spot_price, mark_price, basis_spread_pct, funding_rate_8h, annualized_apr, funding_regime, action, funding_collected_usd, fees_paid_usd, net_pnl_usd, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, log_tuple)
                conn.commit()
                return cursor.rowcount
        except Exception as ex:
            return 1

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

    def init_paper_campaign_metadata(self, campaign_id: str, started_at: int, required_end_at: int, min_settlements: int, config_hash: str) -> bool:
        query = """
        INSERT OR IGNORE INTO paper_campaign_metadata
        (campaign_id, started_at, required_end_at, min_required_settlements, carry_strategy_hash, status)
        VALUES (?, ?, ?, ?, ?, 'ACTIVE');
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (campaign_id, started_at, required_end_at, min_settlements, config_hash))
            conn.commit()
            return cursor.rowcount > 0

    def insert_campaign_event(self, campaign_id: str, event_type: str, details: str, config_hash: str) -> int:
        import csv
        ts_now = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        
        # Compute chained SHA256 digest
        prev_hash = "GENESIS_HASH"
        if os.path.exists(self.events_csv):
            try:
                import pandas as pd
                df_ev = pd.read_csv(self.events_csv)
                if not df_ev.empty and 'hash' in df_ev.columns:
                    prev_hash = str(df_ev['hash'].iloc[-1])
            except Exception:
                pass
                
        import hashlib
        payload = f"{prev_hash}:{ts_now}:{campaign_id}:{event_type}:{details}:{config_hash}"
        chained_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]

        # 1. Write to CSV first
        try:
            file_exists = os.path.exists(self.events_csv)
            with open(self.events_csv, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'campaign_id', 'event_type', 'details', 'hash'])
                writer.writerow([ts_now, campaign_id, event_type, details, chained_hash])
        except Exception as ex:
            print(f"  [WARN] Failed to write event row to CSV: {ex}")

        # 2. Insert into SQLite table
        query = """
        INSERT INTO campaign_events (timestamp, campaign_id, event_type, details, hash)
        VALUES (?, ?, ?, ?, ?);
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (ts_now, campaign_id, event_type, details, chained_hash))
                conn.commit()
                return cursor.rowcount
        except Exception:
            return 1

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
