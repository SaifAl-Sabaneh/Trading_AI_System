"""
Dataset Version Registry
========================
Every research experiment must record which dataset version it used.
This file is the canonical registry of all historical dataset versions.

Usage in experiment manifests:
    dataset_version: "v1"
    dataset_registry: "database/dataset_versions.py"

To add a new version after a major data update:
    1. Run collectors/historical_backfill.py
    2. Run collectors/validate_dataset.py to get checksums + row counts
    3. Append a new entry to DATASET_VERSIONS below
    4. Bump CURRENT_VERSION
"""
import datetime

CURRENT_VERSION = "v1"

DATASET_VERSIONS = {
    "v1": {
        "version":       "v1",
        "description":   "Gold-standard research archive. Binance bulk archives. "
                         "Covers 11 identified market regime events from Nov 2020 through Jul 2024.",
        "created_date":  "2026-07-20",
        "source":        "https://data.binance.vision/data/futures/um/monthly/",
        "data_types":    ["candles_1h", "funding_rates"],
        "symbols": [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
            "SOLUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT",
        ],
        "period_start":  "2020-11-01",
        "period_end":    "2024-07-01",
        "months_covered": 44,
        "regimes_covered": [
            "COVID_CRASH_2020",
            "BULL_MANIA_2021_H1",
            "CRYPTO_SUMMER_CRASH_2021",
            "BULL_MANIA_2021_H2",
            "BEAR_MARKET_2022",
            "LUNA_COLLAPSE_2022",
            "BEAR_CONSOLIDATION_2022",
            "FTX_COLLAPSE_2022",
            "RECOVERY_2023",
            "ETF_LAUNCH_2024",
            "POST_HALVING_2024",
        ],
        # Filled in after validate_dataset.py run:
        "row_counts":    {
            "candles_total":        295464,
            "funding_rates_total":  37038,
            "oi_snapshots_total":   4500,
        },
        "phenomenon_coverage": {
            "extreme_funding_events_btc": 126,   # funding_rate > 0.0008/8h
            "extreme_funding_events_eth": 159,
            "max_funding_rate_btc":       0.00249,
            "max_funding_rate_eth":       0.00375,
        },
        "notes": (
            "First complete version. Raw ZIP archives preserved in raw_data/binance/. "
            "Dataset can be fully rebuilt from raw_data/ without re-downloading. "
            "Validated by collectors/validate_dataset.py. "
            "This version is the prerequisite for re-testing HYP-FUND-REV-V1."
        ),
    }
}


def get_current_version() -> dict:
    """Returns the metadata for the current canonical dataset version."""
    return DATASET_VERSIONS[CURRENT_VERSION]


def describe(version: str = None) -> None:
    """Print a human-readable summary of a dataset version."""
    v = DATASET_VERSIONS.get(version or CURRENT_VERSION, {})
    print(f"\nDataset Version : {v.get('version')}")
    print(f"Description     : {v.get('description')}")
    print(f"Created         : {v.get('created_date')}")
    print(f"Period          : {v.get('period_start')} -> {v.get('period_end')}  ({v.get('months_covered')} months)")
    print(f"Symbols ({len(v.get('symbols', []))})    : {', '.join(v.get('symbols', []))}")
    print(f"Regimes         : {len(v.get('regimes_covered', []))} labelled regimes")
    print(f"Row Counts      : {v.get('row_counts')}")
    print(f"Phenomenon      : {v.get('phenomenon_coverage')}")
    print(f"Notes           : {v.get('notes')}")


if __name__ == "__main__":
    describe()
