-- SQLite Schema Definition for Autonomous Crypto Trading Intelligence System

-- 1. Multi-timeframe Candles (OHLCV)
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
CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol, timeframe, timestamp);

-- 2. Perpetual Funding Rates
CREATE TABLE IF NOT EXISTS funding_rates (
    symbol TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    funding_rate REAL NOT NULL,
    mark_price REAL DEFAULT 0.0,
    PRIMARY KEY (symbol, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_funding_lookup ON funding_rates(symbol, timestamp);

-- 3. Open Interest History
CREATE TABLE IF NOT EXISTS open_interest (
    symbol TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open_interest REAL NOT NULL,
    open_interest_usd REAL DEFAULT 0.0,
    PRIMARY KEY (symbol, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_oi_lookup ON open_interest(symbol, timestamp);

-- 4. Liquidation Snapshots / Force Orders
CREATE TABLE IF NOT EXISTS liquidations (
    symbol TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    usd_value REAL DEFAULT 0.0,
    PRIMARY KEY (symbol, timestamp, side, price)
);
CREATE INDEX IF NOT EXISTS idx_liq_lookup ON liquidations(symbol, timestamp);

-- 5. Market State & Regime Classifier Snapshots
CREATE TABLE IF NOT EXISTS market_state (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    trend_state TEXT NOT NULL,
    volatility_state TEXT NOT NULL,
    liquidity_state TEXT NOT NULL,
    risk_state TEXT NOT NULL,
    regime_score REAL DEFAULT 0.0,
    PRIMARY KEY (symbol, timeframe, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_mkt_state_lookup ON market_state(symbol, timeframe, timestamp);

-- 6. Trade Memory Database (Decision Quality & Multi-Horizon MFE/MAE Logging)
CREATE TABLE IF NOT EXISTS trade_memory (
    trade_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL DEFAULT '1h',
    decision_timestamp INTEGER NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    tier TEXT NOT NULL DEFAULT 'RESEARCH',
    reasons TEXT NOT NULL,
    market_state_snapshot TEXT NOT NULL,
    entry_price REAL,
    exit_price REAL,
    realized_pnl_pct REAL,
    mfe_1h_pct REAL,
    mae_1h_pct REAL,
    mfe_4h_pct REAL,
    mae_4h_pct REAL,
    mfe_24h_pct REAL,
    mae_24h_pct REAL,
    decision_quality_score REAL,
    evaluated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_memory_eval ON trade_memory(evaluated_at);

-- 7. Strategy Performance & Confidence Calibration Statistics
CREATE TABLE IF NOT EXISTS strategy_statistics (
    strategy_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    market_state TEXT NOT NULL,
    confidence_bucket TEXT NOT NULL,
    n_decisions INTEGER DEFAULT 0,
    n_executed INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0.0,
    mean_return_pct REAL DEFAULT 0.0,
    total_return_pct REAL DEFAULT 0.0,
    profit_factor REAL DEFAULT 0.0,
    avg_mfe_pct REAL DEFAULT 0.0,
    avg_mae_pct REAL DEFAULT 0.0,
    calibrated_accuracy REAL DEFAULT 0.0,
    last_updated INTEGER,
    PRIMARY KEY (strategy_name, symbol, timeframe, market_state, confidence_bucket)
);

-- 8. Phase 4 Live Paper Carry Ledger
CREATE TABLE IF NOT EXISTS paper_carry_ledger (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    spot_price REAL NOT NULL,
    mark_price REAL NOT NULL,
    basis_spread_pct REAL NOT NULL,
    funding_rate_8h REAL NOT NULL,
    annualized_apr REAL NOT NULL,
    funding_regime TEXT NOT NULL,
    action TEXT NOT NULL,
    funding_collected_usd REAL DEFAULT 0.0,
    fees_paid_usd REAL DEFAULT 0.0,
    net_pnl_usd REAL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'OBSERVED'
);
CREATE INDEX IF NOT EXISTS idx_paper_ledger ON paper_carry_ledger(symbol, timestamp);

-- 9. Phase 5.1 Position Event Journal
CREATE TABLE IF NOT EXISTS paper_position_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    spot_price REAL NOT NULL,
    mark_price REAL NOT NULL,
    amount_usd REAL DEFAULT 0.0,
    fee_usd REAL DEFAULT 0.0,
    reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_position_events ON paper_position_events(symbol, timestamp);

-- 10. Phase 5.2 Campaign Metadata & Frozen Config Hash
CREATE TABLE IF NOT EXISTS paper_campaign_metadata (
    campaign_id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    required_end_at INTEGER NOT NULL,
    min_required_settlements INTEGER DEFAULT 90,
    carry_strategy_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
);

-- 11. Chronological Campaign Audit Event Log
CREATE TABLE IF NOT EXISTS campaign_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    campaign_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- CAMPAIGN_STARTED, HASH_VERIFIED, OBSERVER_CYCLE, SETTLEMENT_AUDIT, CAMPAIGN_COMPLETED
    details TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_campaign_events ON campaign_events(campaign_id, timestamp);
