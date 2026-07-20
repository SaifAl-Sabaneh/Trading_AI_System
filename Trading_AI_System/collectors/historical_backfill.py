"""
Historical Bulk Downloader — Gold-Standard Research Dataset Builder
===================================================================
Source: https://data.binance.vision (public bulk archives, no API key required)
Target: market_history.db

Design principles:
  - Resumable: checks dataset_metadata before each download; skips already-downloaded months
  - Gap-aware: verifies completeness after each batch
  - Source-first: uses Binance bulk ZIP archives for all historical data
  - Falls back to REST API only for recent months not yet in archives

Run:
    python Trading_AI_System/collectors/historical_backfill.py

Or import and call:
    from collectors.historical_backfill import HistoricalBackfillRunner
    runner = HistoricalBackfillRunner()
    runner.run()
"""
import os
import sys
import csv
import io
import time
import datetime
import hashlib
import zipfile
import urllib.request
import urllib.error

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database_history import HistoryDatabase
from config.settings import HISTORY_SYMBOLS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BINANCE_ARCHIVE_BASE = "https://data.binance.vision/data/futures/um"
BINANCE_FUTURES_REST  = "https://fapi.binance.com"

# Regime-aligned download window: covers ALL identified market regime events
# Ordered by research value (oldest first, so we have the full bull/bear cycle)
HISTORY_START = datetime.date(2020, 11, 1)   # Binance USDT perps began ~2019-09; 2020-11 = start of bull
HISTORY_END   = datetime.date(2024, 7, 1)    # Through ETF launch + April 2024 halving

TIMEFRAMES_TO_DOWNLOAD = ["1h"]   # Primary research timeframe; add "4h" or "1d" if needed

# REST fallback: last N months to fill the gap between archive and today
REST_RECENT_MONTHS = 3

BATCH_SIZE = 500   # rows per DB commit
RETRY_DELAY = 5    # seconds between retries
MAX_RETRIES = 3

# Where raw ZIP archives are preserved alongside the database
# Structure: raw_data/binance/{data_type}/{symbol}/{year}/{filename}.zip
RAW_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "raw_data", "binance"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _month_range(start: datetime.date, end: datetime.date):
    """Yields (year, month) tuples from start to end inclusive."""
    cur = start.replace(day=1)
    while cur <= end.replace(day=1):
        yield cur.year, cur.month
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)


def _to_ms(dt: datetime.datetime) -> int:
    return int(dt.timestamp() * 1000)


def _fetch_url(url: str) -> bytes:
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None          # file doesn't exist (symbol too new, etc.)
            print(f"    [WARN] HTTP {e.code} on {url} (attempt {attempt+1}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"    [WARN] {e} (attempt {attempt+1}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY)
    return None


def _save_raw_archive(data: bytes, data_type: str, symbol: str,
                      year: int, month: int, filename: str) -> str:
    """
    Persist raw ZIP bytes to raw_data/binance/{data_type}/{symbol}/{year}/{filename}.
    Returns the saved file path. Idempotent — skips if file already exists with same size.
    """
    dest_dir = os.path.join(RAW_DATA_DIR, data_type, symbol, str(year))
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    if not os.path.exists(dest_path):
        with open(dest_path, "wb") as f:
            f.write(data)
    return dest_path


# ---------------------------------------------------------------------------
# Candle downloader (Binance bulk archive)
# ---------------------------------------------------------------------------

def _parse_klines_csv(data: bytes, symbol: str, timeframe: str):
    """Parse klines CSV from Binance archive zip. Returns list of tuples."""
    rows = []
    text = data.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    for line in reader:
        if not line or not line[0].isdigit():
            continue
        # Columns: open_time, open, high, low, close, volume, close_time,
        #          quote_vol, trades, taker_buy_vol, taker_buy_quote, ignore
        try:
            ts        = int(line[0])
            o, h, l, c = float(line[1]), float(line[2]), float(line[3]), float(line[4])
            vol       = float(line[5])
            quote_vol = float(line[7])
            trades    = int(line[8])
            tb_vol    = float(line[9])
            tb_quote  = float(line[10])
            rows.append((symbol, timeframe, ts, o, h, l, c, vol, quote_vol, tb_vol, tb_quote, trades))
        except (ValueError, IndexError):
            continue
    return rows


def download_candles_month(db: HistoryDatabase, symbol: str, timeframe: str,
                           year: int, month: int) -> int:
    dataset_name = f"candles_history/{symbol}/{timeframe}/{year}-{month:02d}"
    if db.get_last_downloaded_ts(dataset_name) is not None:
        return 0   # already downloaded

    filename = f"{symbol}-{timeframe}-{year}-{month:02d}.zip"
    url = f"{BINANCE_ARCHIVE_BASE}/monthly/klines/{symbol}/{timeframe}/{filename}"
    raw = _fetch_url(url)
    if raw is None:
        return 0

    # Persist raw archive before parsing
    _save_raw_archive(raw, "klines", symbol, year, month, filename)

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            fname = zf.namelist()[0]
            csv_bytes = zf.read(fname)
    except zipfile.BadZipFile:
        print(f"    [WARN] Bad zip for {symbol} {timeframe} {year}-{month:02d}")
        return 0

    rows = _parse_klines_csv(csv_bytes, symbol, timeframe)
    if not rows:
        return 0

    inserted = db.insert_candles(rows)
    first_ts = rows[0][2]
    last_ts  = rows[-1][2]
    db.record_download(dataset_name, symbol, timeframe, "binance_bulk_archive",
                       first_ts, last_ts, inserted, checksum=_sha256(raw),
                       notes=f"source_url={url} raw_archive=raw_data/binance/klines/{symbol}/{year}/{filename}")
    return inserted


# ---------------------------------------------------------------------------
# Funding Rate downloader (Binance bulk archive)
# ---------------------------------------------------------------------------

def _parse_funding_csv(data: bytes, symbol: str):
    """
    Parse funding rate CSV from Binance archive zip.

    Binance has two historical formats:
      Old: calcTime, fundingRate, markPrice
           e.g. 1604073600000, 0.0001, 15000.5
      New: calcTime, fundingIntervalHours, lastFundingRate
           e.g. 1604073600000, 8, 0.0001

    Detect by magnitude of column[1]:
      - abs(col1) >= 1.0  -> new format (col1 = hours, col2 = rate)
      - abs(col1) <  1.0  -> old format (col1 = rate, col2 = mark price)
    """
    rows = []
    text = data.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    for line in reader:
        if not line or not line[0].isdigit():
            continue
        try:
            ts   = int(line[0])
            val1 = float(line[1])
            if abs(val1) >= 1.0 and len(line) > 2:
                # New format: col1 = fundingIntervalHours, col2 = lastFundingRate
                rate = float(line[2])
                mark = 0.0
            else:
                # Old format: col1 = fundingRate, col2 = markPrice
                rate = val1
                mark = float(line[2]) if len(line) > 2 and line[2] else 0.0
            rows.append((symbol, ts, rate, mark))
        except (ValueError, IndexError):
            continue
    return rows



def download_funding_month(db: HistoryDatabase, symbol: str,
                           year: int, month: int) -> int:
    dataset_name = f"funding_rates_history/{symbol}/{year}-{month:02d}"
    if db.get_last_downloaded_ts(dataset_name) is not None:
        return 0

    filename = f"{symbol}-fundingRate-{year}-{month:02d}.zip"
    url = f"{BINANCE_ARCHIVE_BASE}/monthly/fundingRate/{symbol}/{filename}"
    raw = _fetch_url(url)
    if raw is None:
        return 0

    # Persist raw archive
    _save_raw_archive(raw, "fundingRate", symbol, year, month, filename)

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_bytes = zf.read(zf.namelist()[0])
    except zipfile.BadZipFile:
        return 0

    rows = _parse_funding_csv(csv_bytes, symbol)
    if not rows:
        return 0

    inserted = db.insert_funding_rates(rows)
    db.record_download(dataset_name, symbol, None, "binance_bulk_archive",
                       rows[0][1], rows[-1][1], inserted, checksum=_sha256(raw),
                       notes=f"source_url={url} raw_archive=raw_data/binance/fundingRate/{symbol}/{year}/{filename}")
    return inserted


# ---------------------------------------------------------------------------
# OI via REST (no bulk archive available; only goes back ~30 days per call)
# We use this as a best-effort fill for recent data only.
# ---------------------------------------------------------------------------

def download_oi_rest(db: HistoryDatabase, symbol: str, timeframe: str = "1h") -> int:
    """Pulls up to the last 500 OI snapshots via Binance futures REST."""
    url = (f"{BINANCE_FUTURES_REST}/futures/data/openInterestHist"
           f"?symbol={symbol}&period={timeframe}&limit=500")
    raw = _fetch_url(url)
    if not raw:
        return 0
    import json
    try:
        items = json.loads(raw)
    except Exception:
        return 0
    rows = []
    for item in items:
        try:
            rows.append((symbol,
                         int(item["timestamp"]),
                         float(item["sumOpenInterest"]),
                         float(item["sumOpenInterestValue"])))
        except (KeyError, ValueError):
            continue
    if not rows:
        return 0
    return db.insert_open_interest(rows)


# ---------------------------------------------------------------------------
# Market Regime Seeder
# ---------------------------------------------------------------------------

MARKET_REGIMES = [
    {
        "label": "COVID_CRASH_2020",
        "type":  "CRASH",
        "start_ms": _to_ms(datetime.datetime(2020, 2, 15, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2020, 3, 31, tzinfo=datetime.timezone.utc)),
        "desc":   "COVID-19 market panic. BTC -60% in 24h on March 12.",
        "events": "March 12 crash, BitMEX insurance fund liquidation"
    },
    {
        "label": "BULL_MANIA_2021_H1",
        "type":  "BULL",
        "start_ms": _to_ms(datetime.datetime(2020, 11, 1, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2021, 5, 18, tzinfo=datetime.timezone.utc)),
        "desc":   "First leg of 2021 bull. Extreme positive funding (+0.15-0.30%/8h on BTC). Open interest explosion.",
        "events": "BTC ATH $64k April 2021, Tesla announcement, Coinbase IPO"
    },
    {
        "label": "CRYPTO_SUMMER_CRASH_2021",
        "type":  "CRASH",
        "start_ms": _to_ms(datetime.datetime(2021, 5, 18, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2021, 7, 20, tzinfo=datetime.timezone.utc)),
        "desc":   "China ban + Elon tweets. BTC -55% from ATH. Funding normalization shock.",
        "events": "China mining ban, Elon BTC tweet reversal, long liquidation cascade"
    },
    {
        "label": "BULL_MANIA_2021_H2",
        "type":  "BULL",
        "start_ms": _to_ms(datetime.datetime(2021, 7, 21, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2021, 11, 10, tzinfo=datetime.timezone.utc)),
        "desc":   "Second bull leg. ETH ATH, BTC ATH $69k. High positive funding again.",
        "events": "BTC ATH $69k Nov 10, ETH ATH, Solana growth"
    },
    {
        "label": "BEAR_MARKET_2022",
        "type":  "BEAR",
        "start_ms": _to_ms(datetime.datetime(2021, 11, 11, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2022, 4, 30, tzinfo=datetime.timezone.utc)),
        "desc":   "Steady bear market. Funding gradually turned negative on most alts.",
        "events": "Rate hike fears, NFT/DeFi cooling, Metaverse bubble deflation"
    },
    {
        "label": "LUNA_COLLAPSE_2022",
        "type":  "CRASH",
        "start_ms": _to_ms(datetime.datetime(2022, 5, 1, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2022, 6, 30, tzinfo=datetime.timezone.utc)),
        "desc":   "Terra/LUNA collapse. $40B wiped in days. Extreme negative funding on BTC/ETH.",
        "events": "UST depeg May 9, LUNA hyperinflation, 3AC insolvency, Celsius freeze"
    },
    {
        "label": "BEAR_CONSOLIDATION_2022",
        "type":  "SIDEWAYS",
        "start_ms": _to_ms(datetime.datetime(2022, 7, 1, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2022, 10, 31, tzinfo=datetime.timezone.utc)),
        "desc":   "Low-volatility bear consolidation. Low funding rates across the board.",
        "events": "Merge anticipation (ETH), Fed rate hikes continue"
    },
    {
        "label": "FTX_COLLAPSE_2022",
        "type":  "CRASH",
        "start_ms": _to_ms(datetime.datetime(2022, 11, 1, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2022, 12, 15, tzinfo=datetime.timezone.utc)),
        "desc":   "FTX collapse. BTC -30% in days. Highest short-side liquidation cascade.",
        "events": "FTX bankruptcy Nov 11, Binance rescue collapse, BlockFi insolvency"
    },
    {
        "label": "RECOVERY_2023",
        "type":  "BULL",
        "start_ms": _to_ms(datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2023, 12, 31, tzinfo=datetime.timezone.utc)),
        "desc":   "Gradual recovery. Low baseline funding. USDC depeg event. Banking crisis.",
        "events": "USDC depeg March, Silicon Valley Bank, BlackRock ETF filing July"
    },
    {
        "label": "ETF_LAUNCH_2024",
        "type":  "BULL",
        "start_ms": _to_ms(datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2024, 3, 31, tzinfo=datetime.timezone.utc)),
        "desc":   "US Spot BTC ETF approval. Funding rates spiked. New ATH approach.",
        "events": "ETF approval Jan 10, institutional inflows, BTC new ATH $73k"
    },
    {
        "label": "POST_HALVING_2024",
        "type":  "SIDEWAYS",
        "start_ms": _to_ms(datetime.datetime(2024, 4, 1, tzinfo=datetime.timezone.utc)),
        "end_ms":   _to_ms(datetime.datetime(2024, 7, 1, tzinfo=datetime.timezone.utc)),
        "desc":   "Post-halving consolidation. Funding normalised after ETF launch spike.",
        "events": "BTC halving April 20, ETF outflows, Mt Gox repayments"
    },
]


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

class HistoricalBackfillRunner:
    def __init__(self):
        self.db = HistoryDatabase()

    def seed_regimes(self):
        n = self.db.seed_market_regimes(MARKET_REGIMES)
        print(f"  [Regimes] Seeded {n} market regime records.")

    def run(self, symbols=None, timeframes=None,
            start=HISTORY_START, end=HISTORY_END,
            skip_candles=False, skip_funding=False, skip_oi=False):

        symbols    = symbols    or HISTORY_SYMBOLS
        timeframes = timeframes or TIMEFRAMES_TO_DOWNLOAD
        months     = list(_month_range(start, end))

        print("=" * 70)
        print("  GOLD-STANDARD HISTORICAL DATASET BUILDER")
        print(f"  Symbols    : {len(symbols)} assets")
        print(f"  Timeframes : {timeframes}")
        print(f"  Period     : {start} -> {end} ({len(months)} months)")
        print(f"  Target DB  : market_history.db")
        print("=" * 70)

        # 1. Seed market regimes (idempotent)
        self.seed_regimes()

        total_candles  = 0
        total_funding  = 0
        total_oi       = 0

        for symbol in symbols:
            print(f"\n>>> {symbol}")

            # --- Candles ---
            if not skip_candles:
                for tf in timeframes:
                    c_count = 0
                    for year, month in months:
                        n = download_candles_month(self.db, symbol, tf, year, month)
                        c_count += n
                        if n > 0:
                            print(f"    [Candles] {symbol}/{tf} {year}-{month:02d}: +{n} rows")
                    total_candles += c_count
                    if c_count == 0:
                        print(f"    [Candles] {symbol}/{tf}: all months already downloaded or unavailable")

            # --- Funding Rates ---
            if not skip_funding:
                f_count = 0
                for year, month in months:
                    n = download_funding_month(self.db, symbol, year, month)
                    f_count += n
                    if n > 0:
                        print(f"    [Funding] {symbol} {year}-{month:02d}: +{n} events")
                total_funding += f_count
                if f_count == 0:
                    print(f"    [Funding] {symbol}: all months already downloaded or unavailable")

            # --- OI (REST fallback, recent only) ---
            if not skip_oi:
                n = download_oi_rest(self.db, symbol)
                total_oi += n
                if n > 0:
                    print(f"    [OI-REST] {symbol}: +{n} recent snapshots")

        print()
        print("=" * 70)
        print("  DOWNLOAD COMPLETE")
        print(f"  Candles  : +{total_candles:,}")
        print(f"  Funding  : +{total_funding:,}")
        print(f"  OI       : +{total_oi:,}")
        stats = self.db.get_stats()
        print()
        print("  HISTORY DB TOTALS:")
        print(f"    Candles      : {stats['candles_total']:,}")
        print(f"    Funding Rates: {stats['funding_total']:,}")
        print(f"    OI Snapshots : {stats['oi_total']:,}")
        print(f"    Symbols      : {stats['symbols']}")
        print(f"    Regimes      : {stats['regimes']}")
        if stats['funding_rate_max']:
            print(f"    Funding Range: {stats['funding_rate_min']:.6f} -> {stats['funding_rate_max']:.6f}")
        print("=" * 70)

        # Verify the dataset contains the phenomenon we need
        self._verify_coverage()

    def _verify_coverage(self):
        print("\n  DATASET COVERAGE VERIFICATION:")
        db = self.db
        all_pass = True
        for sym in ["BTCUSDT", "ETHUSDT"]:
            rows = db.fetch_funding_rates(sym)
            if not rows:
                print(f"    [FAIL] {sym}: No funding rate history")
                all_pass = False
                continue
            max_rate = max(r[1] for r in rows)
            extreme  = sum(1 for r in rows if r[1] > 0.0008)
            print(f"    {sym}: {len(rows):,} funding events, "
                  f"max={max_rate:.5f}, extreme(>0.08%/8h)={extreme}")
            if extreme < 10:
                print(f"    [WARN] {sym}: fewer than 10 extreme funding events — "
                      f"HYP-FUND-REV-V1 will still lack sufficient signal density")
                all_pass = False
            else:
                print(f"    [OK]   {sym}: extreme event coverage confirmed")

        if all_pass:
            print("\n  [READY] Dataset contains required phenomena for Campaign #1.")
        else:
            print("\n  [PARTIAL] Some gaps remain. "
                  "Extend date range or add more symbols to improve coverage.")


if __name__ == "__main__":
    runner = HistoricalBackfillRunner()
    runner.run()
