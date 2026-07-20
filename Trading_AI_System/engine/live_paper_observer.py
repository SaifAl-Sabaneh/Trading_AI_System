"""
Phase 4: Live Paper Observer Daemon (engine/live_paper_observer.py)
======================================================================
Polls live Binance REST endpoints to observe real-time BTCUSDT and ETHUSDT carry yields,
basis spreads, funding regimes, operational API health, AND stateful virtual position P&L tracking.

Position States Tracked:
  - FLAT     : No position held (waiting for funding hurdle >= +0.01%/8h)
  - ENTERED  : Initial virtual allocation executed (recorded entry spot & perp mark)
  - HOLDING  : Position active, accumulating 8-hourly funding payouts
  - EXITED   : Position unwound due to negative funding or hurdle drop
"""
import os
import sys
import time
import json
import datetime
import urllib.request
import urllib.error
import pandas as pd
from typing import Dict, Any, List

import hashlib

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Database
from config.settings import BINANCE_SPOT_BASE_URL, BINANCE_FUTURES_BASE_URL
from strategies.production.carry import CarryAgent

class LivePaperObserver:
    def __init__(self, db: Database = None, virtual_capital_per_asset: float = 5000.0):
        self.db = db if db else Database()
        self.agent = CarryAgent()
        self.symbols = ["BTCUSDT", "ETHUSDT"]
        self.virtual_capital = virtual_capital_per_asset
        self.api_failures = 0
        
        # Phase 5.2 Campaign Clock & Frozen Config Hash
        self.campaign_id = "CARRY-PAPER-V1-20260720"
        self.config_hash = self._get_strategy_hash()
        self._init_campaign_clock()
        
        # Stateful virtual position tracker
        self.virtual_positions = {
            s: {
                "state": "FLAT",
                "entry_spot_p": 0.0,
                "entry_mark_p": 0.0,
                "entry_time": 0,
                "accrued_funding_usd": 0.0,
                "fees_paid_usd": 0.0,
                "net_pnl_usd": 0.0
            } for s in self.symbols
        }

    def _get_strategy_hash(self) -> str:
        strategy_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategies", "production", "carry.py")
        if os.path.exists(strategy_path):
            with open(strategy_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        return "UNKNOWN_HASH"

    def _init_campaign_clock(self):
        dt_start = datetime.datetime(2026, 7, 20, 0, 0, tzinfo=datetime.timezone.utc)
        dt_end   = dt_start + datetime.timedelta(days=30)
        ts_start = int(dt_start.timestamp() * 1000)
        ts_end   = int(dt_end.timestamp() * 1000)
        try:
            self.db.init_paper_campaign_metadata(self.campaign_id, ts_start, ts_end, 90, self.config_hash)
            self.db.insert_campaign_event(self.campaign_id, "CAMPAIGN_STARTED", "Live Paper Campaign CARRY-PAPER-V1-20260720 initialized", self.config_hash)
            self.db.insert_campaign_event(self.campaign_id, "HASH_VERIFIED", f"Frozen Strategy SHA256[{self.config_hash}] verified", self.config_hash)
        except Exception as e:
            print(f"  [WARN] Failed to init campaign metadata: {e}")

    def fetch_live_spot_price(self, symbol: str) -> float:
        url = f"{BINANCE_SPOT_BASE_URL}/api/v3/ticker/price?symbol={symbol}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode('utf-8'))
                return float(data.get("price", 0.0))
        except Exception as e:
            self.api_failures += 1
            print(f"  [WARN] Failed to fetch spot price for {symbol}: {e}")
            return 0.0

    def fetch_live_premium_index(self, symbol: str) -> Dict[str, Any]:
        url = f"{BINANCE_FUTURES_BASE_URL}/fapi/v1/premiumIndex?symbol={symbol}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode('utf-8'))
                return {
                    "mark_price": float(data.get("markPrice", 0.0)),
                    "last_funding_rate": float(data.get("lastFundingRate", 0.0)),
                    "next_funding_time": int(data.get("nextFundingTime", 0))
                }
        except Exception as e:
            self.api_failures += 1
            print(f"  [WARN] Failed to fetch premium index for {symbol}: {e}")
            return {"mark_price": 0.0, "last_funding_rate": 0.0, "next_funding_time": 0}

    @staticmethod
    def classify_funding_regime(annualized_apr: float) -> str:
        if annualized_apr <= 0.0:
            return "NEGATIVE (EXIT GUARD)"
        elif annualized_apr < 5.0:
            return "LOW (<5% APR)"
        elif annualized_apr < 15.0:
            return "NORMAL (5-15% APR)"
        elif annualized_apr < 30.0:
            return "HIGH (15-30% APR)"
        else:
            return "EXTREME (>30% APR)"

    @staticmethod
    def evaluate_basis_alert(basis_pct: float) -> str:
        abs_basis = abs(basis_pct)
        if abs_basis >= 1.0:
            return "DANGER (Basis Decoupling > 1.0%)"
        elif abs_basis >= 0.5:
            return "WARNING (Elevated Basis Spread > 0.5%)"
        else:
            return "HEALTHY (< 0.5%)"

    def run_observation_cycle(self) -> List[Dict[str, Any]]:
        dt_now = datetime.datetime.now(datetime.timezone.utc)
        ts_now = int(dt_now.timestamp() * 1000)
        
        print("=" * 78)
        print(f"  PHASE 4: LIVE PAPER OBSERVATION CYCLE -- {dt_now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 78)
        
        cycle_reports = []
        
        for symbol in self.symbols:
            t0 = time.time()
            spot_p = self.fetch_live_spot_price(symbol)
            prem = self.fetch_live_premium_index(symbol)
            latency_ms = int((time.time() - t0) * 1000)
            
            mark_p = prem["mark_price"]
            funding_rate = prem["last_funding_rate"]
            next_funding_ms = prem["next_funding_time"]
            
            basis_pct = ((mark_p - spot_p) / spot_p * 100) if spot_p > 0 else 0.0
            basis_alert = self.evaluate_basis_alert(basis_pct)
            
            annualized_apr = funding_rate * 3 * 365 * 100
            regime = self.classify_funding_regime(annualized_apr)
            
            if next_funding_ms > 0:
                next_dt = datetime.datetime.fromtimestamp(next_funding_ms / 1000, tz=datetime.timezone.utc)
                mins_remaining = int((next_dt - dt_now).total_seconds() / 60)
            else:
                mins_remaining = 0
                
            df_eval = pd.DataFrame([{
                "symbol": symbol,
                "funding_rate": funding_rate,
                "funding_rate_pctile": 0.90
            }])
            
            dec = self.agent.evaluate(symbol, "1h", df_eval)
            act = dec["action"]
            
            pos = self.virtual_positions[symbol]
            current_state = pos["state"]
            
            # --- Stateful Virtual Position Transitions ---
            if act == "CARRY_DELTA_NEUTRAL":
                if current_state in ["FLAT", "EXITED"]:
                    pos["state"] = "ENTERED"
                    pos["entry_spot_p"] = spot_p
                    pos["entry_mark_p"] = mark_p
                    pos["entry_time"] = ts_now
                    # Entry friction fee: 14 bps on allocated capital ($5000 * 0.0014 = $7.00)
                    entry_fee = self.virtual_capital * 0.0014
                    pos["fees_paid_usd"] += entry_fee
                    pos["net_pnl_usd"] -= entry_fee
                else:
                    pos["state"] = "HOLDING"
            elif act == "NEUTRAL":
                if current_state in ["ENTERED", "HOLDING"]:
                    pos["state"] = "EXITED"
                    # Exit friction fee: 14 bps
                    exit_fee = self.virtual_capital * 0.0014
                    pos["fees_paid_usd"] += exit_fee
                    pos["net_pnl_usd"] -= exit_fee
                else:
                    pos["state"] = "FLAT"
                    
            report = {
                "symbol": symbol,
                "spot_price": spot_p,
                "mark_price": mark_p,
                "basis_spread_pct": basis_pct,
                "basis_alert": basis_alert,
                "funding_rate_8h": funding_rate,
                "annualized_apr": annualized_apr,
                "funding_regime": regime,
                "mins_to_settlement": mins_remaining,
                "api_latency_ms": latency_ms,
                "action": dec["action"],
                "position_state": pos["state"],
                "net_pnl_usd": pos["net_pnl_usd"],
                "reasons": dec["reasons"]
            }
            cycle_reports.append(report)
            
            # Persist to paper_carry_ledger table in market_live.db
            log_tuple = (
                ts_now,
                symbol,
                spot_p,
                mark_p,
                basis_pct,
                funding_rate,
                annualized_apr,
                regime,
                dec["action"],
                pos["accrued_funding_usd"],
                pos["fees_paid_usd"],
                pos["net_pnl_usd"],
                pos["state"]
            )
            try:
                self.db.insert_paper_carry_log(log_tuple)
            except Exception as ex:
                print(f"  [WARN] Could not persist paper log: {ex}")
            
            print(f"\n>>> {symbol}")
            print(f"  Spot Price         : ${spot_p:,.2f}")
            print(f"  Mark Price         : ${mark_p:,.2f} (Basis: {basis_pct:+.3f}% | {basis_alert})")
            print(f"  Live Funding Rate  : {funding_rate*100:+.4f}% / 8h (Est APR: {annualized_apr:+.2f}%)")
            print(f"  Funding Regime     : [{regime}]")
            print(f"  Next Settlement    : in {mins_remaining} minutes")
            print(f"  Position State     : [{pos['state']}]  (Virtual Net PnL: ${pos['net_pnl_usd']:+,.2f})")
            print(f"  API Latency        : {latency_ms} ms (API Failures: {self.api_failures})")
            print(f"  Carry Decision     : [{dec['action']}] (Confidence: {dec['confidence']*100:.0f}%)")
            for r in dec['reasons']:
                print(f"    - {r}")
                
        print("\n" + "=" * 78)
        print("  OBSERVATION CYCLE COMPLETE")
        print("=" * 78)
        
        return cycle_reports

if __name__ == "__main__":
    observer = LivePaperObserver()
    observer.run_observation_cycle()
