from typing import Dict, Any, Tuple

class RiskEngine:
    def __init__(self, max_pos_pct: float = 0.10, min_confidence: float = 0.60, min_rr_ratio: float = 1.5):
        self.max_pos_pct = max_pos_pct
        self.min_confidence = min_confidence
        self.min_rr_ratio = min_rr_ratio

    def evaluate_opportunity(self, decision: Dict[str, Any], account_balance: float = 200.0) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Evaluates a candidate decision against strict risk limits.
        Returns: (is_approved, veto_reason, approved_trade_params)
        """
        action = decision.get("action", "NEUTRAL")
        confidence = decision.get("confidence", 0.0)
        exp_ret = decision.get("expected_return_pct", 0.0)
        exp_risk = decision.get("expected_risk_pct", 0.001)

        if action == "NEUTRAL":
            return False, "Action is NEUTRAL", {}

        # Rule 1: Confidence Hurdle
        if confidence < self.min_confidence:
            return False, f"Confidence {confidence:.2f} below threshold {self.min_confidence:.2f}", {}

        # Rule 2: Risk-Reward Ratio
        rr_ratio = exp_ret / (exp_risk + 1e-9)
        if rr_ratio < self.min_rr_ratio and action not in ["CARRY_DELTA_NEUTRAL", "CARRY_REVERSE_NEUTRAL"]:
            return False, f"Risk-Reward Ratio {rr_ratio:.2f} below minimum {self.min_rr_ratio:.2f}", {}

        # Rule 3: Position Size Cap
        pos_size_usd = account_balance * self.max_pos_pct
        
        approved_trade = {
            "symbol": decision["symbol"],
            "action": action,
            "allocated_capital_usd": pos_size_usd,
            "max_pos_pct": self.max_pos_pct,
            "confidence": confidence,
            "expected_return_pct": exp_ret,
            "expected_risk_pct": exp_risk,
            "reasons": decision.get("reasons", [])
        }
        
        return True, "APPROVED", approved_trade

if __name__ == "__main__":
    risk_eng = RiskEngine()
    test_dec = {
        "symbol": "BTCUSDT",
        "action": "BUY",
        "confidence": 0.75,
        "expected_return_pct": 0.03,
        "expected_risk_pct": 0.01,
        "reasons": ["Bullish stack"]
    }
    approved, reason, trade = risk_eng.evaluate_opportunity(test_dec)
    print(f"Approval status: {approved} ({reason})")
    print("Trade:", trade)
