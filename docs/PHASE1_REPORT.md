# AlphaForge AI — Phase 1 Technical Report (Deterministic Core)

**Datathon PolyFinances × AWS × Banque Nationale (2026)**  
**Team:** AlphaForge AI  
**Repository Branch:** `mvp-backend`  
**Date:** 2026-11-14  
**Status:** Phase 1 Complete (Deterministic Core & Verifier Operational)

---

## 1. Executive Summary & Deliverables Built

Phase 1 establishes the mathematical and deterministic foundation of the AlphaForge AI investment decision-support platform. In accordance with the core design principle — **the LLM calculates nothing; all figures derive from deterministic tools and registered evidence** — all financial data processing, calendar alignment, currency normalization, portfolio optimization, stress testing, evidence registration, rule governance, and anti-hallucination verification have been fully implemented in Python.

### Core Modules Implemented

```
alphaforge/
├── app/
│   ├── __init__.py
│   ├── evidence.py          # EvidenceRegistry (E1..En audit trail)
│   ├── governance.py        # Rule engine (crypto blocking, TSLA incoherence, caps)
│   ├── personas.py          # Amira, Mateo, Robert structured specifications
│   ├── verifier.py          # Anti-hallucination deterministic verifier
│   └── tools/
│       ├── __init__.py
│       ├── prices.py        # Calendar union, FX CAD conversion, data quality report
│       ├── risk.py          # Volatility, max DD, CVaR95, beta vs XIU.TO, risk contributions
│       ├── optimize.py      # cvxpy constrained min-variance & Spinu risk parity
│       └── stress.py        # 2022 stagflation replay, rolling windows, cap sensitivity
├── scripts/
│   └── run_personas.py      # End-to-end multi-persona pipeline execution
└── tests/
    ├── test_tools.py        # Unit tests for prices, risk, optimize, stress
    ├── test_verifier.py     # Anti-hallucination & deliberate error rejection tests
    └── test_personas.py     # End-to-end integration tests for all 3 personas
```

---

## 2. Quantitative Methodology & Data Transformations

Every data transformation has been documented with its exact source, date, and currency:

1. **Exchange Calendar Unification:**
   - **Sources:** Toronto Stock Exchange (TSX) and U.S. Exchanges (NYSE, NASDAQ, Cboe BZX, NYSE Arca).
   - **Methodology:** Constructed the unified calendar $C = \text{TSX} \cup \text{US}$ (1,282 trading days from 2021-11-12 to 2026-11-12).
   - **Continuous Asset Resampling:** 24/7 cryptoassets (BTC-USD, ETH-USD, 1,827 calendar days) were resampled to match exchange trading days.
   - **Gap Treatment:** Forward-fill applied up to `limit=3` days for single-market statutory holidays (e.g., Canadian Thanksgiving vs. U.S. Thanksgiving). Initial 783 missing values reduced to **0** missing values across all 31 assets.

2. **Foreign Exchange Conversion to CAD:**
   - **Source:** Bank of Canada Valet API (`FXUSDCAD`).
   - **Methodology:** Backward as-of alignment with strictly zero look-ahead bias. Where U.S. markets traded on Canadian bank holidays (37 days), the last published Bank of Canada fixing was carried forward. All USD asset prices $P^{\text{USD}}_t$ were converted to CAD:
     $$P^{\text{CAD}}_t = P^{\text{USD}}_t \times \text{FX}^{\text{USDCAD}}_t$$
   - Canadian `.TO` tickers were preserved in native CAD.
   - Daily returns were computed as logarithmic returns: $r_t = \ln(P^{\text{CAD}}_t / P^{\text{CAD}}_{t-1})$ (1,281 observations).

3. **Data Quality & Anomaly Audit (`prices.generate_data_quality_report`):**
   - **CNQ.TO 1.021 Split Anomaly:** Documented that the 1.021 split ratio on 2022-08-22 was a cash/distribution anomaly, not an actual share split. Verified that `adj_close` already incorporates dividend adjustments and splits, preventing double-counting.
   - **Macroeconomic Look-Ahead Lag:** Documented that monthly series (`CPIAUCSL`, `STATIC_TOTALCPICHANGE`, `UNRATE`) are indexed to their observation month but published 2 to 4 weeks later; model conditioning must apply a 30-day lag.
   - **Survivorship Bias:** Documented that the curated universe of 31 assets was selected in November 2026, creating an inherent retrospective bias.

4. **Risk Analytics Engine (`risk.py`):**
   - **Annualized Volatility:** $\sigma_{\text{ann}} = \text{std}(r) \times \sqrt{252}$.
   - **Maximum Drawdown:** $\text{MDD} = \min_\tau \left( \frac{P_\tau - \max_{t \le \tau} P_t}{\max_{t \le \tau} P_t} \right)$.
   - **CVaR95 (Expected Shortfall):** Average daily loss in the worst 5% tail: $-\mathbb{E}[r \mid r \le q_{0.05}]$.
   - **Beta vs. XIU.TO:** $\beta = \text{Cov}(r_p, r_{\text{XIU.TO}}) / \text{Var}(r_{\text{XIU.TO}})$.
   - **Risk Decomposition:** Component and percentage risk contributions ($\%RC_i = \frac{w_i (\Sigma w)_i}{w^T \Sigma w}$) summing exactly to 100%.

5. **Constrained Convex Optimization (`optimize.py`):**
   - Implemented constrained Quadratic Programming with `cvxpy` (OSQP / SCS solvers).
   - Strict adherence to official case guidelines: **zero expected return forecasting**. The optimizer minimizes portfolio variance subject to per-asset caps, sector caps/floors, class caps/floors, and exclusions, or solves Spinu convex risk parity.

6. **Deterministic Anti-Hallucination Verifier (`verifier.py`):**
   - Validates that every cited Evidence ID exists in `EvidenceRegistry`.
   - Extracts all numeric tokens from generated claims.
   - Confirms that every number in the claim is grounded in the cited evidence item (accounting for percentages, decimals, signs, and rounding).
   - Automatically catches and rejects hallucinated numbers, incorrect evidence citations, and unsupported statistics.

---

## 3. Test Suite & Verification Results

The test suite consists of 28 comprehensive unit and integration tests across all quantitative tools, verifier failure modes, and persona pipelines.

### Test Execution Command
```bash
/home/wilson-lab/Datathon-Poly/.venv/bin/pytest -v alphaforge/tests
```

### Pytest Execution Summary
```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.2.0, pluggy-1.7.0 -- /home/wilson-lab/Datathon-Poly/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/wilson-lab/Datathon-Poly/repo
plugins: anyio-4.16.0, platformdirs-4.14.5
collecting ... collected 28 items

alphaforge/tests/test_personas.py::TestPersonasEndToEnd::test_amira_pipeline PASSED [  3%]
alphaforge/tests/test_personas.py::TestPersonasEndToEnd::test_mateo_pipeline PASSED [  7%]
alphaforge/tests/test_personas.py::TestPersonasEndToEnd::test_robert_baseline_pipeline PASSED [ 10%]
alphaforge/tests/test_personas.py::TestPersonasEndToEnd::test_robert_reality_check_governance_block PASSED [ 14%]
alphaforge/tests/test_personas.py::TestPersonasEndToEnd::test_robert_capped_alternative_pipeline PASSED [ 17%]
alphaforge/tests/test_tools.py::TestPricesTool::test_load_starter_data PASSED [ 21%]
alphaforge/tests/test_tools.py::TestPricesTool::test_calendar_union PASSED [ 25%]
alphaforge/tests/test_tools.py::TestPricesTool::test_cad_conversion PASSED [ 28%]
alphaforge/tests/test_tools.py::TestPricesTool::test_data_quality_report PASSED [ 32%]
alphaforge/tests/test_tools.py::TestRiskTool::test_annualized_volatility PASSED [ 35%]
alphaforge/tests/test_tools.py::TestRiskTool::test_max_drawdown PASSED   [ 39%]
alphaforge/tests/test_tools.py::TestRiskTool::test_cvar95 PASSED         [ 42%]
alphaforge/tests/test_tools.py::TestRiskTool::test_beta_vs_benchmark PASSED [ 46%]
alphaforge/tests/test_tools.py::TestRiskTool::test_portfolio_risk_metrics PASSED [ 50%]
alphaforge/tests/test_tools.py::TestRiskTool::test_risk_contributions_sum_to_one PASSED [ 53%]
alphaforge/tests/test_tools.py::TestOptimizeTool::test_min_variance_basic PASSED [ 57%]
alphaforge/tests/test_tools.py::TestOptimizeTool::test_min_variance_sector_and_class_constraints PASSED [ 60%]
alphaforge/tests/test_tools.py::TestOptimizeTool::test_risk_parity_equal_risk PASSED [ 64%]
alphaforge/tests/test_tools.py::TestStressTool::test_stress_test_2022_episode PASSED [ 67%]
alphaforge/tests/test_tools.py::TestStressTool::test_rolling_risk_windows PASSED [ 71%]
alphaforge/tests/test_tools.py::TestStressTool::test_sensitivity_to_asset_cap PASSED [ 75%]
alphaforge/tests/test_verifier.py::TestVerifier::test_number_extraction PASSED [ 78%]
alphaforge/tests/test_verifier.py::TestVerifier::test_percentage_and_sign_equivalence PASSED [ 82%]
alphaforge/tests/test_verifier.py::TestVerifier::test_valid_explanation_passes PASSED [ 85%]
alphaforge/tests/test_verifier.py::TestVerifier::test_deliberate_error_non_existent_evidence_id PASSED [ 89%]
alphaforge/tests/test_verifier.py::TestVerifier::test_deliberate_error_hallucinated_number PASSED [ 92%]
alphaforge/tests/test_verifier.py::TestVerifier::test_deliberate_error_number_without_evidence_citation PASSED [ 96%]
alphaforge/tests/test_verifier.py::TestVerifier::test_deliberate_error_wrong_evidence_cited PASSED [100%]

============================== 28 passed in 2.84s ==============================
```

---

## 4. Persona Execution Results & Reality Tests

Pipeline executed via `alphaforge/scripts/run_personas.py`:

### Persona 1: Amira
- **Profile:** 26 years old, Software Engineer, High Risk, 15+ years horizon.
- **Reality Test:** Accommodate growth interest in tech and crypto without interpreting "high risk" as "anything goes"; maintain real diversification.
- **Allocations:**
  - `ENB.TO`: 10.0%, `FTS.TO`: 10.0%, `GLD`: 10.0%, `JNJ`: 10.0%
  - `MSFT`: 9.7%, `CSU.TO`: 8.9%, `PG`: 6.9%, `AAPL`: 6.4%, `TD.TO`: 6.2%, `XOM`: 6.0%, `RY.TO`: 5.9%
  - `BTC-USD`: 5.0%, `ZST.TO`: 5.0%
  - **Tech Total:** 25.0% (capped $\le 40\%$). **Crypto Total:** 5.0% (capped $\le 15\%$).
- **Risk Metrics (CAD):**
  - Annualized Volatility: **9.83%**
  - Maximum Drawdown: **-12.73%**
  - CVaR95: **1.38%**
  - Beta vs XIU.TO: **0.5596**
  - Active Assets: **13**
- **2022 Stress Episode Drawdown:** **-12.73%** (vs. -21.65% for SPY in CAD).
- **Governance & Verifier:** Passed; 100% numerical verification valid.

---

### Persona 2: Mateo
- **Profile:** 41 years old, Operations Manager, Moderate Risk, 8–12 years horizon.
- **Reality Test:** Integrate non-financial criteria (ESG preferences and controversy avoidance) alongside financial risk/return balance.
- **Allocations:**
  - Core ESG: `ESGV`: 15.0% (ESG-screened U.S. equity).
  - Fixed Income: `ZST.TO`: 25.0%, `XBB.TO`: 13.2%, `AGG`: 11.8% (Total Fixed Income: 50.0%).
  - Core Defensives & TSX: `FTS.TO`: 10.0%, `GLD`: 7.7%, `JNJ`: 6.0%, `RY.TO`: 3.2%, `CNQ.TO`: 3.1%, `TD.TO`: 2.0%, `ENB.TO`: 1.9%, `PG`: 0.9%, `ATD.TO`: 0.1%.
  - Speculative Exclusions: `BTC-USD`: 0.0%, `ETH-USD`: 0.0%.
  - High-Carbon / Controversy Exclusion: `XOM`: 0.0% (traditional energy capped $\le 5\%$).
- **Risk Metrics (CAD):**
  - Annualized Volatility: **5.34%**
  - Maximum Drawdown: **-7.68%**
  - CVaR95: **0.75%**
  - Beta vs XIU.TO: **0.2959**
  - Active Assets: **13**
- **2022 Stress Episode Drawdown:** **-7.26%**.
- **Governance & Verifier:** Passed; 100% numerical verification valid.

---

### Persona 3: Robert (Baseline & Reality Test)
- **Profile:** 59 years old, Healthcare Professional, Low-to-Moderate Risk, 3–5 years horizon (near retirement).
- **Reality Test:** Know how to challenge an ungrounded request (hyped speculative opportunity like TSLA), explain risk, and avoid blindly complying.

#### 1. Baseline Allocation (Capital Preservation)
- **Allocations:** Fixed Income: `ZST.TO` 35.0%, `XBB.TO` 26.1%, `AGG` 22.3% (Total Fixed Income: 83.4%). TSX/US Blue Chips: `RY.TO` 3.3%, `XOM` 2.4%, `TD.TO` 2.2%, `CNQ.TO` 1.7%, `JNJ` 1.7%, `ENB.TO` 1.4%, `GLD` 1.3%, `FTS.TO` 1.1%, `MSFT` 0.7%, `ATD.TO` 0.6%, `JPM` 0.2%, `CNR.TO` 0.1%.
- **Risk Metrics:** Volatility: **3.56%**, Max Drawdown: **-5.48%**, 2022 Stress Drawdown: **-5.48%**.
- **Active Assets:** 15.

#### 2. Reality Test: Unconstrained Speculative Request
- **Scenario:** Robert requests 20% in Tesla (`TSLA`) and 5% in Bitcoin (`BTC-USD`).
- **Governance Results:** **Failed (`passed = False`, `has_blocking = True`)**.
  - `[BLOQUANT] crypto_prohibition_robert`: Crypto-assets are strictly prohibited for Robert's 3-5 year capital preservation profile.
  - `[ATTENTION] robert_tsla_incoherence`: Incoherence detected between Robert's 3-5 year horizon and TSLA's 58.2% annualized volatility and -70.9% historical drawdown.
  - `[ATTENTION] single_asset_concentration`: TSLA (20%) exceeds single asset cap of 8.0%.
  - **Proposed Action:** Constructive refusal; propose capped alternative of at most 3.0% TSLA satellite.

#### 3. Capped Alternative Execution
- **Allocations with 3% TSLA Satellite:** `ZST.TO`: 35.0%, `XBB.TO`: 25.3%, `AGG`: 21.7%, **`TSLA`: 3.0%**, `XOM`: 2.8%, `JNJ`: 2.4%, `FTS.TO`: 2.4%, `RY.TO`: 1.8%, `ENB.TO`: 1.6%, `GLD`: 1.4%, `CNQ.TO`: 1.4%, `TD.TO`: 1.1%, `ATD.TO`: 0.2%.
- **Risk Metrics:**
  - Annualized Volatility: **4.00%** (mild increase from 3.56%).
  - Maximum Drawdown: **-6.11%** (historical drawdown contained).
  - 2022 Episode Drawdown: **-6.11%**.
  - Fixed Income Maintained: **82.0%**.
- **Governance Status:** **Passed (`passed = True`, zero blocking alerts)**.
- **Verifier Status:** Valid.

---

## 5. Case vs. Plan Nuances & Contradictions Flagged

1. **Prescriptive vs. Illustrative Persona Constraints:**
   - *Case Specification:* Personas in the official brief provide behavioral and situational reference scenarios, not rigid quantitative quotas.
   - *Team Plan:* Defined explicit quantitative caps (e.g., tech $\le 40\%$, crypto $\le 15\%$, bonds $\ge 50\%$).
   - *Resolution:* Marked in code and documentation as explicit **team assumptions**.

2. **Hyped Opportunity (Robert):**
   - *Case Specification:* Describes "a highly publicized company even when it is riskier than he would normally prefer" without hardcoding the ticker in the text.
   - *Starter Pack & Team Plan:* Identifies `TSLA` (and `NVDA`) as the concrete exemplars.
   - *Resolution:* Verified with `TSLA` while keeping the governance logic generalized for any high-volatility single equity ($>35\%$ vol or $>40\%$ drawdown).

3. **No Chain of Thought Exposure:**
   - *Case Specification:* Section 4 explicitly instructs prototypes to explain outputs *"without inventing justifications or exposing detailed internal model reasoning"*.
   - *Resolution:* The explainability architecture is strictly anchored to observable tool execution records ($E_1 \dots E_n$) and verified by `verifier.py`.

---

## 6. Open Questions & Roadmap for Phase 2

1. **AWS Bedrock Integration:**
   - Connect `boto3` Bedrock client (region `us-east-1`, profile `datathon`) using verified model IDs:
     - `global.anthropic.claude-sonnet-5-5` (Orchestrator, Analyst, Explainer)
     - `global.anthropic.claude-opus-5-5` (Governance escalation on ambiguous queries)
     - `amazon.titan-embed-text-v2:0` (Document retrieval / RAG)
   - Implement Converse API call wrappers with structured Pydantic JSON parsing (no forced `tool_choice`).

2. **FastAPI & Streaming SSE:**
   - Implement `POST /api/analyze` and `GET /api/runs/{id}/stream` to stream observable tool execution steps and evidence IDs in real time.

3. **Streamlit Interactive UI:**
   - Build persona cards (Amira, Mateo, Robert), interactive capital allocation doughnut chart, 2022 stress replay graph, and clickable `[E#]` evidence drawer.
