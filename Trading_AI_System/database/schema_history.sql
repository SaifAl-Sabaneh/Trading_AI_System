-- =============================================================================
-- market_history.db Schema
-- Gold-standard research archive. Read-mostly. Never used by live execution.
-- =============================================================================

-- 1. OHLCV Candle History (all symbols, all timeframes, multi-year)
CREATE TABLE IF NOT EXISTS candles_history (
    symbol      TEXT    NOT NULL,
    timeframe   TEXT    NOT NULL,
    timestamp   INTEGER NOT NULL,   -- Unix milliseconds (ms)
    open        REAL    NOT NULL,
    high        REAL    NOT NULL,
    low         REAL    NOT NULL,
    close       REAL    NOT NULL,
    volume      REAL    NOT NULL,
    quote_volume  REAL  DEFAULT 0.0,
    taker_buy_volume REAL DEFAULT 0.0,    -- buyer-initiated volume (from Binance archive)
    taker_buy_quote  REAL DEFAULT 0.0,
    trades_count  INTEGER DEFAULT 0,
    PRIMARY KEY (symbol, timeframe, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_ch_lookup ON candles_history(symbol, timeframe, timestamp);

-- 2. Funding Rate History (full perpetual funding history)
CREATE TABLE IF NOT EXISTS funding_rates_history (
    symbol        TEXT    NOT NULL,
    timestamp     INTEGER NOT NULL,   -- funding settlement timestamp (ms)
    funding_rate  REAL    NOT NULL,   -- raw rate (e.g. 0.0001 = 0.01%/8h)
    mark_price    REAL    DEFAULT 0.0,
    PRIMARY KEY (symbol, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_fr_lookup ON funding_rates_history(symbol, timestamp);

-- 3. Open Interest History (hourly snapshots, sourced from Binance futures data)
CREATE TABLE IF NOT EXISTS open_interest_history (
    symbol          TEXT    NOT NULL,
    timestamp       INTEGER NOT NULL,
    open_interest   REAL    NOT NULL,   -- contract units
    open_interest_usd REAL  DEFAULT 0.0,
    PRIMARY KEY (symbol, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_oi_lookup ON open_interest_history(symbol, timestamp);

-- 4. Liquidation History (force-order events)
CREATE TABLE IF NOT EXISTS liquidations_history (
    symbol      TEXT    NOT NULL,
    timestamp   INTEGER NOT NULL,
    side        TEXT    NOT NULL,   -- 'BUY' (long liquidated) or 'SELL' (short liquidated)
    quantity    REAL    NOT NULL,
    price       REAL    NOT NULL,
    usd_value   REAL    DEFAULT 0.0,
    PRIMARY KEY (symbol, timestamp, side, price)
);
CREATE INDEX IF NOT EXISTS idx_liq_lookup ON liquidations_history(symbol, timestamp);

-- =============================================================================
-- 5. Dataset Metadata
-- Records every download batch: source, timestamp, row count, checksum.
-- Every experiment must record which dataset_version it used.
-- =============================================================================
CREATE TABLE IF NOT EXISTS dataset_metadata (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_name        TEXT    NOT NULL,   -- e.g. 'candles_history/BTCUSDT/1h'
    symbol              TEXT,
    timeframe           TEXT,
    source              TEXT    NOT NULL,   -- 'binance_bulk_archive' | 'binance_rest'
    first_timestamp     INTEGER,            -- earliest row in this batch (ms)
    last_timestamp      INTEGER,            -- latest row in this batch (ms)
    row_count           INTEGER DEFAULT 0,
    checksum_sha256     TEXT,               -- SHA-256 of the raw bytes downloaded
    download_timestamp  INTEGER NOT NULL,   -- when this download was recorded (ms)
    status              TEXT    DEFAULT 'complete',  -- 'complete' | 'partial' | 'failed'
    notes               TEXT,
    UNIQUE (dataset_name, first_timestamp, last_timestamp)
);

-- =============================================================================
-- 6. Market Regimes
-- Formally labelled historical market regimes.
-- Experiments query this table to run regime-stratified analysis.
-- =============================================================================
CREATE TABLE IF NOT EXISTS market_regimes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    regime_label    TEXT    NOT NULL,   -- e.g. 'BULL_MANIA_2021'
    regime_type     TEXT    NOT NULL,   -- 'BULL' | 'BEAR' | 'CRASH' | 'SIDEWAYS' | 'EVENT'
    start_timestamp INTEGER NOT NULL,   -- ms
    end_timestamp   INTEGER NOT NULL,   -- ms
    description     TEXT,
    key_events      TEXT,               -- comma-separated notable events
    max_funding_rate_observed REAL,     -- to later fill in after download
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_regime_time ON market_regimes(start_timestamp, end_timestamp);
