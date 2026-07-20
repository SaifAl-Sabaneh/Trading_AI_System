import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 9 Liquid Perpetual Futures — Full research universe
TARGET_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "ADAUSDT",
]

# Symbols available from inception of Binance perpetuals (2020+)
# Used for maximum historical coverage in backfill
HISTORY_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "SOLUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "AVAXUSDT",
]

# 6 Standard Timeframes
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

# Live Database — small, fast, used by execution engine
DB_PATH          = os.path.join(BASE_DIR, "database", "market_live.db")
SCHEMA_PATH      = os.path.join(BASE_DIR, "database", "schema.sql")

# History Database — large, read-mostly, research archive
HISTORY_DB_PATH     = os.path.join(BASE_DIR, "database", "market_history.db")
HISTORY_SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema_history.sql")

# Data Collection Settings
HTTP_TIMEOUT_SECS = 15
MAX_RETRIES = 3
BINANCE_SPOT_BASE_URL = "https://api.binance.com"
BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"

# Risk Governor Defaults
ACCOUNT_VALIDATION_BALANCE_USD = 200.0
MAX_POSITION_SIZE_PCT = 0.10     # Max 10% capital allocated per position
MIN_CONFIDENCE_THRESHOLD = 0.60   # Minimum 60% confidence to approve trade
MIN_RISK_REWARD_RATIO = 1.5       # Minimum 1.5 R/R ratio required

# Simulation / Execution Friction Defaults
TAKER_FEE_BPS = 5.0              # 0.05% taker fee
MAKER_FEE_BPS = 2.0              # 0.02% maker fee
SLIPPAGE_BPS_MAJOR = 3.0         # 0.03% slippage for BTC/ETH
SLIPPAGE_BPS_ALT = 10.0          # 0.10% slippage for SOL/BNB/XRP/DOGE/AVAX
LATENCY_DELAY_SECS = 2.0         # 2-second execution delay simulation
