# ISSUE #4 Notes — ESG flags and screening tool (Mateo)

## What was delivered
- `data/esg/esg_flags.csv`: sourced ESG screening flags for the 31-ticker universe (methodology-aligned to Vanguard ESGV / FTSE US All Cap Choice exclusions where verified), with evidence and source metadata.
- `data/esg/SOURCES.md`: source list, URLs, dates, license/terms notes, and methods used.
- `alphaforge/app/tools/esg.py`: pure/offline helpers:
  - `load_esg_flags(path=None) -> pandas.DataFrame`
  - `esg_screen(tickers, flags_df=None, path=None) -> {excluded, flagged, unverified, evidence}`
- `alphaforge/tests/test_esg.py`: pytest coverage for loading, classification, unknown tickers, and preloaded DataFrame usage.

## Screening semantics
- `exclude`: ticker has at least one sourced row with `status=exclude` (e.g. fossil fuel production/oil sands/pipelines categories evidenced against FTSE Choice exclusions).
- `flag`: ticker has at least one `status=flag` row and no `exclude` rows (reserved for softer/warn cases; can be extended with sourced controversies).
- `ok`: explicitly verified acceptable for a checked criterion (e.g. ESGV as ESG-screened benchmark ETF in this pass).
- `non_verifie`: no sufficient company-specific sourced evidence was fetched/verified in this pass for exclusion/controversy determination (or asset type not assessed at holdings level). **Do not invent facts.**

`esg_screen` returns:
- `excluded`: tickers with any `exclude`
- `flagged`: tickers with any `flag` and no `exclude`
- `unverified`: tickers with neither `exclude` nor `flag` (including absent tickers)
- `evidence`: all flag rows for requested tickers

## How to wire into Mateo's persona later (without editing restricted files now)
> Constraint respected: no edits to `personas.py`, `governance.py`, `pipeline.py`, `alphaforge/app/agents/*`, or `frontend/*` in this issue.

Suggested integration points for a follow-up PR/issue:

1. **Persona constraints (Mateo)** in `alphaforge/app/personas.py` (or persona config source):
   - Call `esg_screen(candidate_tickers)` when building/validating Mateo's investable universe.
   - Hard-remove `excluded` tickers from eligible assets for allocation.
   - Treat `flagged` as warnings requiring explanation/evidence surfacing; treat `unverified` as "non vérifié" (do not present as compliant).

2. **Governance checks** in `alphaforge/app/governance.py`:
   - Add a deterministic rule: if any proposed weight > 0 for `excluded` tickers under Mateo, emit a blocking alert citing `evidence` rows (`source_url`, `document_page`, `evidence_text`).
   - Add attention/info alerts for `flagged`/`unverified` holdings with evidence IDs/links in the run trace.

3. **Pipeline/orchestrator** in `alphaforge/app/pipeline.py` (and agents as applicable):
   - Load flags once via `load_esg_flags()` and pass to `esg_screen`.
   - Persist screening results as evidence artifacts so the explainer/verifier can cite them (no LLM-invented ESG claims).
   - When a user requests an excluded/controversial name (e.g. fossil fuel exposure for Mateo), return a refusal/alternative framed by sourced evidence.

4. **UI trace** (frontend, later): display excluded/flagged/unverified buckets and clickable `source_url` (+ page/date) per ticker.

## Extending coverage safely
- Add rows only when backed by a fetched public source URL; include quote/paraphrase, date, retrieval date, and license/terms note.
- Prefer company sustainability/annual reports, regulator filings, or index methodology documents for controversy and exclusion claims.
- Keep statuses conservative: use `non_verifie` rather than guessing.
