# Institutional Quantitative Research Protocol & Promotion Committee

This document defines the 11-gate governance protocol for evaluating and classifying all market phenomena and strategy hypotheses:

$$\text{Market Phenomenon} \xrightarrow{\quad\text{Scientific Promotion (Gates 0--7)}\quad} \text{Candidate Strategy} \xrightarrow{\quad\text{Economic Deployment (Gates 8--11)}\quad} \text{Production Trading}$$

---

## 1. Layer 1: Scientific Promotion Committee (Gates 0 – 7)

Evaluates whether a true, un-overfitted statistical or structural phenomenon exists in empirical market data:

### Gate 0: Information Edge & Burden of Proof
- **Requirement**: Identify what non-trivial, constrained, or institutional market information this hypothesis observes that average participants are not already fully pricing.
- **Higher Burden Rule**: If a hypothesis relies *only* on widely available price-derived technical indicators (EMA, RSI, MACD), it bears a **substantially higher burden of proof** and must identify an explicit behavioral or execution constraint to be considered.

### Gate 1: Economic Constraint Mechanism
- **Requirement**: Identify exactly *who is economically constrained*, *why they cannot avoid paying*, and *why that constraint will persist*.
- **Examples**: Leveraged longs paying funding to shorts during bull sentiment; exchange liquidation engines submitting forced market orders.

### Gate 2: Pre-Registered Hypothesis Protocol
- **Requirement**: Target parameters, feature definitions, and exit rules must be pre-committed in an immutable YAML manifest (`governance/evidence_manifests/*.yaml`) *before* observing out-of-sample test windows.

### Gate 3: Minimum Out-Of-Sample (OOS) Sample Size ($n \ge 100$)
- **Requirement**: Must accumulate at least **$n \ge 100$ independent Out-Of-Sample trade observations**.
- **Rule**: Any result with $n < 100$ where the required market conditions DID occur is classified as `INCONCLUSIVE`.
- **Distinct Rule**: If the required market conditions were **absent from the dataset entirely**, the result is classified as `UNTESTED`. This is not a failure of the hypothesis — it is a dataset limitation.

### Gate 4: Out-Of-Sample Profit Factor ($PF \ge 1.20$)
- **Requirement**: Out-of-sample gross profits divided by gross losses must equal or exceed **$1.20$** after deducting 14 bps taker fees and market slippage.

### Gate 5: Net Positive Expectancy ($E > +0.10\%$)
- **Requirement**: Expected return per trade after friction must be strictly positive ($E > +0.10\%$).

### Gate 6: Monte Carlo Permutation Significance ($p < 0.01$)
- **Requirement**: Under 1,000 label-shuffled Monte Carlo permutations, the strategy's observed Sharpe ratio must achieve statistical significance at $p < 0.01$.

### Gate 7: Multi-Regime & Multi-Asset Stability
- **Requirement**: Positive expectancy maintained across at least 3 liquid assets (`BTC`, `ETH`, `SOL`) and across high- and low-volatility regimes.

*Output*: **Candidate Strategy**

---

## 2. Layer 2: Economic Deployment Committee (Gates 8 – 11)

Evaluates whether a validated Candidate Strategy is economically worth deploying for our specific capital size and operational profile:

### Gate 8: Capital Efficiency & Yield Hurdle
- **Requirement**: Annualized net return per dollar deployed relative to operational complexity ($> 10\%$ APR for active capital allocation).

### Gate 9: Operational Burden & Margin Utilization
- **Requirement**: Evaluation of VPS overhead, exchange API rate limits, transfer costs, and liquidation distance.

### Gate 10: Formal Investment Committee Sign-Off
- **Requirement**: Written sign-off document recorded in `governance/signoffs/`.

### Gate 11: Independent Reproducibility Gate
- **Requirement**: Starting strictly from `Raw Data + Hypothesis Manifest + Seed`, an independent script (`governance/reproducibility_verifier.py`) must produce **100% mathematically identical evaluation outputs**.

*Output*: **Production Trading Authority**

---

## 3. Formal 5-Category Strategy Classification Registry

Every strategy hypothesis is classified into exactly one of 5 mutually exclusive categories:

| Category | Definition | Criteria | Current Assignments |
| :--- | :--- | :--- | :--- |
| **PRODUCTION CANDIDATE** | Passed all 11 gates. Trading capital authorised. | Gates 0–11 all passed | **`CarryAgent`** *(Delta-Neutral Funding Carry)* |
| **INCONCLUSIVE** | Required market conditions existed in dataset; statistics insufficient. | Conditions present, $n < 100$ OOS events | **`LiquidationAgent`** *(n=6 OOS, n=17 IS)* |
| **UNTESTED** | Required market conditions were **absent from the dataset**. Hypothesis is on hold pending data acquisition. | Conditions never occurred in available data window | **`FundingReversionAgent`** *(14-day window, no extreme funding events observed)* |
| **RESEARCH SANDBOX** | Quarantined hypothesis or multi-factor feature input. Not yet at Gate 0. | Pre-Gate 0 | N/A |
| **FALSIFIED** | Conditions existed. Failed Gate 0 or OOS Profit Factor ($PF < 1.0$) after sufficient data. | PF < 1.0 with $n \ge 100$ | **`MomentumAgent`** *(OOS PF 0.62)*, **`MeanReversionAgent`** *(OOS PF 0.19)* |

---

## 4. Classification Decision Rules

When a campaign scan returns 0 or insufficient signals, the following decision tree applies:

```
Campaign scan complete
    |
    ├── n >= 100 and PF >= 1.20    --> PRODUCTION CANDIDATE
    |
    ├── n >= 100 and PF < 1.0      --> FALSIFIED
    |
    ├── 0 < n < 100 AND conditions existed in data
    |       --> INCONCLUSIVE (dataset too small; acquire more data)
    |
    ├── n = 0 or near-zero AND conditions absent from window
    |       --> UNTESTED (wrong regime window; acquire phenomenon-covering data)
    |
    └── (none of above)            --> RESEARCH SANDBOX
```

**Key distinction**: `INCONCLUSIVE` means the experiment ran but lacked statistical power.
`UNTESTED` means the experiment could not run because the market never exhibited the required conditions.
These are not the same, and should never be conflated.
