"""
Dataset Validation Report
=========================
Runs after a historical backfill to verify completeness.

For each symbol/timeframe/period, computes:
  - Expected bar count (based on timeframe interval and calendar days)
  - Actual downloaded bar count
  - Missing bars (gaps)
  - Duplicate count
  - Funding extreme event coverage (required for HYP-FUND-REV-V1)
  - Raw archive file count on disk
  - Overall PASS / WARN / FAIL status

No silent failures.

Usage:
    python Trading_AI_System/collectors/validate_dataset.py
"""
import os
import sys
import datetime
import math

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database_history import HistoryDatabase
from config.settings import HISTORY_SYMBOLS, HISTORY_DB_PATH

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BARS_PER_DAY = {"1m": 1440, "5m": 288, "15m": 96, "1h": 24, "4h": 6, "1d": 1}
TIMEFRAMES_VALIDATED = ["1h"]

HISTORY_START = datetime.date(2020, 11, 1)
HISTORY_END   = datetime.date(2024,  7,  1)

# Phenomenon coverage thresholds
EXTREME_FUNDING_THRESHOLD  = 0.0008   # +0.08%/8h — minimum for HYP-FUND-REV-V1
MIN_EXTREME_EVENTS_PER_SYM = 50       # need at least 50 extreme funding events to test

# -----------------------------------------------------------------------
# Physical sanity bounds for funding rates
# Source: Binance perpetual funding rate limits & extreme historic events
#   - Normal range  : -0.005 to +0.005  (-0.5% to +0.5% per 8h)
#   - Hard cap      : +/-0.0075 for most pairs; +/-0.020 for SOL during FTX crash
#   - IMPOSSIBLE    : abs(rate) > 0.025 (schema error, unit mismatch, column swap)
# If ANY of these trigger, the funding data must be rejected before analysis.
# -----------------------------------------------------------------------
FUNDING_SANITY_MAX    = 0.025   # abs rate above this = impossible, FAIL
FUNDING_SANITY_WARN   = 0.005   # abs rate above this in avg = suspicious, WARN
FUNDING_EXTREME_RATIO_WARN = 0.20  # if >20% of events are "extreme", data is suspect

RAW_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "raw_data", "binance")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expected_bars(timeframe: str, start: datetime.date, end: datetime.date) -> int:
    """Approximate expected bar count (accounts for whole days only)."""
    days = (end - start).days
    return days * BARS_PER_DAY.get(timeframe, 24)


def _count_raw_archives(data_type: str, symbol: str) -> int:
    base = os.path.join(RAW_DATA_DIR, data_type, symbol)
    if not os.path.exists(base):
        return 0
    count = 0
    for root, _, files in os.walk(base):
        count += sum(1 for f in files if f.endswith(".zip"))
    return count


def _status(missing_pct: float, has_extreme: bool, expected: int, actual: int) -> str:
    if actual == 0:
        return "FAIL  (no data)"
    if missing_pct > 5.0:
        return f"WARN  ({missing_pct:.1f}% gaps)"
    if not has_extreme:
        return "WARN  (no extreme funding events — insufficient for HYP-FUND-REV-V1)"
    return "PASS"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def run_validation(db: HistoryDatabase = None) -> None:
    if db is None:
        db = HistoryDatabase()

    total_days = (HISTORY_END - HISTORY_START).days
    print()
    print("=" * 78)
    print("  DATASET VALIDATION REPORT")
    print(f"  DB      : {HISTORY_DB_PATH}")
    print(f"  Period  : {HISTORY_START} -> {HISTORY_END}  ({total_days} days)")
    print(f"  Symbols : {len(HISTORY_SYMBOLS)}")
    print("=" * 78)

    start_ms = int(datetime.datetime(HISTORY_START.year, HISTORY_START.month, HISTORY_START.day,
                                     tzinfo=datetime.timezone.utc).timestamp() * 1000)
    end_ms   = int(datetime.datetime(HISTORY_END.year, HISTORY_END.month, HISTORY_END.day,
                                     tzinfo=datetime.timezone.utc).timestamp() * 1000)

    all_pass = True

    # --- Candles ---
    print(f"\n{'Symbol':<12} {'TF':<4} {'Expected':>9} {'Actual':>9} {'Missing':>9} {'Gap%':>6}  {'RawZIPs':>8}  Status")
    print("-" * 78)

    for symbol in HISTORY_SYMBOLS:
        for tf in TIMEFRAMES_VALIDATED:
            expected = _expected_bars(tf, HISTORY_START, HISTORY_END)
            rows = db.fetch_candles(symbol, tf, start_ms, end_ms)
            actual = len(rows)
            missing = max(0, expected - actual)
            gap_pct = (missing / expected * 100) if expected > 0 else 100.0
            raw_count = _count_raw_archives("klines", symbol)

            # Duplicate check
            timestamps = [r[0] for r in rows]
            dupes = len(timestamps) - len(set(timestamps))

            # Funding coverage check (done separately, shown inline)
            fr_rows = db.fetch_funding_rates(symbol, start_ms, end_ms)
            extreme_count = sum(1 for r in fr_rows if abs(r[1]) >= EXTREME_FUNDING_THRESHOLD)
            has_extreme = extreme_count >= MIN_EXTREME_EVENTS_PER_SYM

            status = _status(gap_pct, has_extreme, expected, actual)
            if "FAIL" in status or "WARN" in status:
                all_pass = False

            dupe_note = f" [{dupes} dupes!]" if dupes > 0 else ""
            print(f"{symbol:<12} {tf:<4} {expected:>9,} {actual:>9,} {missing:>9,} {gap_pct:>5.1f}%  {raw_count:>8}  {status}{dupe_note}")

    # --- Funding Rate Sanity Bounds + Summary ---
    print()
    print("  FUNDING RATE SANITY CHECKS (physical plausibility):")
    print(f"  Impossible threshold : abs(rate) > {FUNDING_SANITY_MAX} = schema error")
    print(f"  Suspicious threshold : abs(avg)  > {FUNDING_SANITY_WARN} = unit mismatch risk")
    print(f"  Extreme ratio warn   : extreme/total > {FUNDING_EXTREME_RATIO_WARN*100:.0f}%")
    print()
    print(f"{'Symbol':<12} {'FR Events':>9} {'Extreme(>0.08%)':>16} {'Max Rate':>10} {'AvgRate':>9}  Funding Status")
    print("-" * 82)

    for symbol in HISTORY_SYMBOLS:
        fr_rows = db.fetch_funding_rates(symbol, start_ms, end_ms)
        if not fr_rows:
            print(f"{symbol:<12} {'0':>9} {'—':>16} {'—':>10} {'—':>9}  FAIL (no funding data)")
            all_pass = False
            continue

        rates = [r[1] for r in fr_rows]
        max_abs   = max(abs(r) for r in rates)
        avg_rate  = sum(rates) / len(rates)
        extreme_count = sum(1 for r in rates if abs(r) >= EXTREME_FUNDING_THRESHOLD)
        extreme_ratio = extreme_count / len(rates)

        # --- Sanity gates (ordered by severity) ---
        if max_abs > FUNDING_SANITY_MAX:
            fr_status = (f"FAIL  (IMPOSSIBLE VALUE: max={max_abs:.4f} > {FUNDING_SANITY_MAX}. "
                         f"Schema error or column swap. DO NOT RUN CAMPAIGN.")
            all_pass = False
        elif extreme_ratio > FUNDING_EXTREME_RATIO_WARN:
            fr_status = (f"FAIL  (EXTREME RATIO {extreme_ratio*100:.1f}% > "
                         f"{FUNDING_EXTREME_RATIO_WARN*100:.0f}%. "
                         f"Likely data/unit error. DO NOT RUN CAMPAIGN.)")
            all_pass = False
        elif abs(avg_rate) > FUNDING_SANITY_WARN:
            fr_status = (f"WARN  (avg={avg_rate:.5f} suspiciously high — verify units)")
            all_pass = False
        elif extreme_count >= MIN_EXTREME_EVENTS_PER_SYM:
            fr_status = "PASS"
        else:
            fr_status = f"WARN  (only {extreme_count} extreme events, need >= {MIN_EXTREME_EVENTS_PER_SYM})"
            all_pass = False

        raw_count = _count_raw_archives("fundingRate", symbol)
        print(f"{symbol:<12} {len(fr_rows):>9,} {extreme_count:>16,} {max_abs:>10.5f} {avg_rate:>9.5f}  {fr_status}")

    # --- Market Regimes ---
    print()
    regimes = db.fetch_regimes()
    print(f"\nMarket Regimes Seeded: {len(regimes)}")
    for r in regimes:
        start_dt = datetime.datetime.fromtimestamp(r['start_timestamp'] / 1000, tz=datetime.timezone.utc).date()
        end_dt   = datetime.datetime.fromtimestamp(r['end_timestamp']   / 1000, tz=datetime.timezone.utc).date()
        print(f"  [{r['regime_type']:<8}] {r['regime_label']:<30}  {start_dt} -> {end_dt}")

    # --- Raw Archive Inventory ---
    print()
    total_raw_size_mb = 0.0
    if os.path.exists(RAW_DATA_DIR):
        for root, _, files in os.walk(RAW_DATA_DIR):
            for f in files:
                total_raw_size_mb += os.path.getsize(os.path.join(root, f)) / (1024 * 1024)
    print(f"Raw Archive Total Size: {total_raw_size_mb:.1f} MB  ({RAW_DATA_DIR})")

    # --- Summary ---
    stats = db.get_stats()
    print()
    print("=" * 78)
    print("  SUMMARY")
    print(f"  Total Candles      : {stats['candles_total']:>12,}")
    print(f"  Total Funding Rates: {stats['funding_total']:>12,}")
    print(f"  Total OI Snapshots : {stats['oi_total']:>12,}")
    print(f"  Download Batches   : {stats['download_batches']:>12,}")
    print(f"  Funding Range      : {stats['funding_rate_min']} -> {stats['funding_rate_max']}")
    print()
    if all_pass:
        print("  [PASS] Dataset is complete and contains required phenomena.")
        print("         Ready to re-run Research Campaign #1 (HYP-FUND-REV-V1).")
    else:
        print("  [PARTIAL] Some symbols/fields are incomplete.")
        print("         Re-run historical_backfill.py to fill gaps (resumable).")
    print("=" * 78)


if __name__ == "__main__":
    run_validation()
