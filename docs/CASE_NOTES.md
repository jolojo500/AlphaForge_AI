# AlphaForge AI — Case Notes & Alignment Analysis

> **Executive Alignment Check: Case vs. docs/PLAN.md**
>
> **Potential Contradictions & Nuances Flagged:**
> 1. **Prescriptive vs. Illustrative Persona Constraints:**
>    - *Official Case:* Personas are described purely through qualitative guidelines, objectives, horizons, and behavioral tests (e.g., Amira wants high risk with diversification; Mateo wants balanced growth with ESG screening; Robert wants capital preservation with a 3-5 year horizon but gets tempted by a hyped asset). The case explicitly states: *"The personas and example tickers in the brief are reference points, not a checklist."*
>    - *Team Plan (`docs/PLAN.md`):* Sets exact numerical constraints (e.g., Amira: single asset $\le 10\%$, crypto $\le 10\text{--}15\%$, tech $\le 35\text{--}40\%$; Robert: fixed income $\ge 50\%$, crypto $0\%$).
>    - *Resolution / Alignment:* `PLAN.md` correctly marks these specific thresholds as **team assumptions**. In documentation and code, we must explicitly declare these numerical parameters as operationalizations/team assumptions rather than case-mandated constants.
>
> 2. **Hyped Opportunity (Robert):**
>    - *Official Case:* Mentions *"a highly publicized company even when it is riskier than he would normally prefer"* without hardcoding the company name in the main case description.
>    - *Team Plan & Starter Pack:* Hardcodes Tesla (`TSLA`) as the primary test asset (supported by the starter dataset README which notes `TSLA` and `NVDA` as volatile candidates for Robert's test).
>    - *Resolution / Alignment:* Retain `TSLA` (and `NVDA`) as the concrete test cases for Robert, but keep the governance logic generalized so any speculative/high-volatility request triggers the incoherence warning and alternative proposal.
>
> 3. **Chain of Thought (CoT) & Explainability:**
>    - *Official Case:* Explicitly warns: *"without inventing justifications or exposing detailed internal model reasoning"* (French: *"sans inventer de justification ni exposer les raisonnements internes détaillés des modèles"*).
>    - *Team Plan:* Correctly specifies: *"ne pas exposer la chaîne de pensée du modèle (expliquer via actions observables : appels d'outils, preuves)"*. Explanations must be grounded entirely in observable tool outputs and evidence IDs ($E_1, E_2, \dots$), never raw hidden CoT tokens.
>
> 4. **No Future Return Predictions:**
>    - *Official Case:* Stresses that the goal is NOT to predict future returns from past performance. Past performance does not guarantee future results.
>    - *Team Plan:* Conforms strictly: optimization uses minimum variance / risk parity under constraints and target volatility, with zero expected return forecasting.

---

## 1. Official Personas (Exact Case Specifications)

### Persona 1: Amira
- **Age & Profession:** 26 years old • Software engineer.
- **Family & Experience:** Single, no children, intermediate investment experience.
- **Investment Objective:** Grow capital over the long term.
- **Horizon:** 15 years or more.
- **Risk Profile:** High.
- **Preferences & Constraints:**
  - Very interested in artificial intelligence and emerging technologies.
  - Open to high-growth companies and significant volatility.
  - Interested in crypto assets.
  - Still wants some diversification and does not want to invest exclusively in technology.
- **Case Reality Test:**
  - *"How much risk will the system accept? It should account for an aggressive profile without interpreting 'high risk' as 'anything goes,' while respecting Amira's desire for diversification."*

### Persona 2: Mateo
- **Age & Profession:** 41 years old • Operations manager.
- **Family & Experience:** Partner and two children, intermediate investment experience.
- **Investment Objective:** Balanced capital growth over the medium and long term.
- **Horizon:** 8–12 years.
- **Risk Profile:** Moderate.
- **Preferences & Constraints:**
  - Places high importance on Environmental, Social, and Governance (ESG) factors.
  - Wants to avoid companies involved in significant environmental or social controversies.
  - Seeks a balance between growth potential and stability.
  - Open to emerging technologies when they fit his risk profile, but has little interest in highly speculative investments.
- **Case Reality Test:**
  - *"Can the system incorporate more than return and risk? It should consider financial factors and personal preferences, rather than selecting solely for potential return."*

### Persona 3: Robert
- **Age & Profession:** 59 years old • Healthcare professional.
- **Family & Experience:** Married, adult children, considering retirement in the next few years, advanced investment experience.
- **Investment Objective:** Preserve capital while maintaining some growth potential.
- **Horizon:** 3–5 years.
- **Risk Profile:** Low to moderate.
- **Preferences & Constraints:**
  - Prefers established companies and investments whose business models he understands.
  - Values stability and company quality; little interest in crypto assets.
  - Follows markets actively and is interested in new opportunities.
  - May be tempted by a highly publicized company even when it is riskier than he would normally prefer.
- **Case Reality Test:**
  - *"Can the system challenge a request that conflicts with the investor's profile? It should identify the tension between Robert's immediate interest and his objectives, explain the risks, and avoid simply agreeing."*

---

## 2. Deliverables (Official Case Requirements)

1. **Prototype & Source Code:**
   - Demonstrable prototype showing a complete use case.
   - Accessible explanation of results: sources, assumptions, key factors, limitations.
   - Code repository and `README.md` covering dependencies, data sources, configuration, and reproduction steps.
2. **Demonstration Video:**
   - Approximately 5 minutes.
   - Walk through the problem, agent roles, data/tools used, result, and end-to-end explanation.
   - Show at least two contrasting investor situations to demonstrate context adaptation.
3. **Technical Documentation:**
   - Concise document covering:
     - Overall logic, agent roles/interactions, controls/governance checks.
     - Methods, models, technologies used and justifications.
     - Data sources, selected universe, processing steps, assumptions.
     - Explainability mechanism with an example connecting conclusion to observable trace.
     - Validations of results/explanations, limitations, and future improvements.
4. **One-Pager:**
   - Maximum 1 page summarizing: problem, agentic approach, originality, data sources, explainability, and concrete user value.

---

## 3. Official Evaluation Grid (Appendix 1)

| Criterion | Weight | Jury Evaluation Focus |
|---|---|---|
| **Solution** | 20% | Relevance of the investment question, innovation, creativity, complete prototype, adaptation to 2 contrasting personas. |
| **Agentic AI** | 20% | Architectural clarity, agents with distinct non-decorative roles, self-explainability, visible execution trace. |
| **Data** | 20% | Rigor in data handling (FX conversion, calendar alignment, corporate actions, survivorship bias), validation, visualization. |
| **UX / UI** | 10% | Intuition, ergonomics, readability of citations, evidence traceability. |
| **AWS Integration** | 15% | Real and demonstrable contribution of AWS (Amazon Bedrock). *Lack of effective integration = disqualification.* |
| **Pitch & Business Value** | 15% | Compelling narrative, commercial relevance (e.g., pre-trade copilot for self-directed brokerage like BNCD), presentation quality. |

---

## 4. Responsible Boundaries & Core Rules

- **Simulation Only:** Strictly no live trading, no execution of orders, no access to real confidential banking accounts.
- **No Personalized Advice:** Outputs are educational simulations and decision aids, not registered financial advice.
- **Fact vs. Hypothesis:** Clear distinction between verifiable historical facts, modeling assumptions, and fictional scenarios.
- **Uncertainty & Limitations:** Prominently communicate model limitations, data publication lags, and historical regime shifts (e.g., 2022 stock-bond correlation breakdown).
- **Faithful & Verifiable Explanations:** Explanations must only reference observable evidence IDs ($E_1, \dots, E_n$). No post-hoc hallucinated justifications. Never expose raw internal model reasoning chains.
