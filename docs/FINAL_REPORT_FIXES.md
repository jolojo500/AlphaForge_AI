# Final report — fix plan and handover

Findings from the judge's final test report (Nov 15, 2026), split into five parallel streams.
The 19 issues are on the board with a `stream:*` label. This page is the entry point: read it
before picking up any of them.

The app is an **educational simulation**. Every number shown must come from an `Evidence` item
and be cited by its id. No advice, no forecast, no buy/sell wording.

## Streams, branches, issues

| Stream | Label | Issues | Owned files |
|---|---|---|---|
| Engine | `stream:engine` | #163 #164 #172 #173 #174 #176 #177 | `alphaforge/nodes/scenarios.py`, `alphaforge/costs.py`, `alphaforge/nodes/quant.py`, tests for these |
| Profile | `stream:profile` | #165 #166 #167 #169 | `alphaforge/nodes/profile.py`, `nodes/screening.py`, `nodes/events.py`, `alphaforge/guardrails.py`, `alphaforge/holdings.py`, `alphaforge/tax.py`, `alphaforge/personas.py`, tests for these |
| Explain | `stream:explain` | #168 #171 | `alphaforge/nodes/explain.py`, `nodes/verifier.py`, `nodes/notes.py`, `nodes/red_team.py`, `tests/fixtures/llm/*`, tests for these |
| Results UI | `stream:ui-results` | #171 #178 #179 #180 #181 | results-page components, `frontend/src/lib/evidenceText.tsx`, new results components |
| Profile UI | `stream:ui-profile` | #170 #175 | `frontend/src/components/onboarding/*`, `ProfileModal.tsx`, `AppHeader.tsx`, `QueryScreen.tsx`, `ReplayRunModal.tsx`, `ResolvedProfileCard.tsx`, `frontend/src/api.ts`, `frontend/src/lib/demoProfiles.ts`, `alphaforge/api/server.py`, `alphaforge/users.py`, `alphaforge/user_dossier.py` |

Shared, append-only (add keys at the end, never reorder): `frontend/src/types.ts`,
`frontend/src/i18n.ts`. Orchestrator-owned, do not edit: `alphaforge/state.py`, `graph.py`,
`config.py`, `evidence.py`, `tracing.py`, `pyproject.toml`.

## Contract already on `main` (PR #162, no behaviour change)

`Profile` gained optional fields:

- `requested_allocation: dict[str, float] | None` — what the question asks for, as weights.
  Keys are universe tickers or the asset-class codes `"crypto"`, `"equity"`, `"bond"`, `"gold"`.
- `requested_vehicle: str | None` — a vehicle named in the question that is outside the universe
  (e.g. `"BTCC.B"`).
- Declared limits as ratios: `max_loss_12m`, `crypto_target_min`, `sector_cap`; plus
  `currency_pref` (`"cad" | "usd" | "mixed"`) and `age_band` (e.g. `"18-29"`).
- `holdings_unanalysed: dict[str, float]` — declared holdings outside the universe, at their
  **declared** weight; `holdings_cash: float | None` — undeclared remainder.

`GraphState.guardrails: list[dict]` is filled by `alphaforge/guardrails.py::check_guardrails`
(entry schema in that file's docstring), already called at the end of `scenarios_node`.

`persona_data` keys sent by the questionnaire (server `_custom_persona`): `max_loss_pct` (percent
number, e.g. 25), `crypto_preference`, `sector_cap_pct`, `currency_preference`, `esg_level`,
`age_band`, `budget_cad`, `account_type` (`tfsa|rrsp|fhsa|non_registered|mixed`), `preferences`
(codes only), `current_holdings`.

## Status at handover (Nov 15, 19:50 UTC)

Claude agents hit the 5-hour limit mid-stream. **Uncommitted work exists in five worktrees**:

| Stream | Worktree | Branch | Last local check |
|---|---|---|---|
| engine | `~/Datathon-Poly/fr-engine` | `final/engine` | ruff clean; 1 failing test: `tests/test_costs.py::test_fx_conversion_cost_assumption` (`KeyError: 'norberts_gambit'`) |
| profile | `~/Datathon-Poly/fr-profile` | `final/profile` | ruff clean; 1 failing test: `tests/test_current_holdings.py::test_parse_holdings_dict` (weights vs dollars) |
| explain | `~/Datathon-Poly/fr-explain` | `final/explain` | ruff clean; 1 failing test: `tests/test_explain.py::test_low_capacity_profile_rejects_crypto_weight_clearly` (new direct-verdict wording) |
| ui-results | `~/Datathon-Poly/fr-ui-results` | `final/ui-results` | 452 tests pass; frontend lint/build to re-check |
| ui-profile | `~/Datathon-Poly/fr-ui-profile` | `final/ui-profile` | 469 tests pass; frontend lint/build to re-check |

To continue a stream: `cd` into the worktree, `git status` (the work is uncommitted), finish the
P0s of that stream first, then P1/P2. Checks:

```bash
export PATH="$HOME/.local/bin:$HOME/.local/node/bin:$PATH"
uv run ruff check . && uv run pytest -q
cd frontend && npm ci && npm run lint && npm run build   # frontend changes only
```

Then push the branch and open one PR per stream, body starting with `Closes #NNN` for each issue
it finishes. No AWS commands, no deploy, no secrets.

## The judge's findings (source text)

Profile tested: age 18–29, CELI/TFSA, 100 000 $, risk tolerance and capacity high, growth,
horizon 20–30 years, max 12-month loss 25 %, crypto "15 % et plus", max 40 % per sector, mixed
CAD/USD, ESG tilt + "Énergie & Ressources", holdings BTC-USD 30 % and SOL 40 %.

### P0

1. **"As requested" ignores the question.** Three different questions (full retirement portfolio,
   keep 50 % crypto, 15 % Bitcoin via BTCC.B) returned the same 7 tech stocks at 14.3 % each,
   0 % crypto, same −41.2 % drawdown. Build it from the parsed question; if the named asset or
   weight is missing, block the run with "Je n'ai pas pu traduire votre demande en portefeuille".
2. **Current portfolio misread.** BTC 30 % + SOL 40 % became "100 % BTC" and a "sell 100 000 $ of
   BTC" order. Never rescale; keep unanalysed holdings at their declared weight, treat the rest as
   cash, compute orders only on known dollar amounts.
3. **Real conflicts missed.** Dossier says "Aucun conflit identifié" while the declared 25 %
   12-month loss is breached (−26.0 % stress, −31.5 % drawdown), crypto is 2.1 % against a "15 %
   et plus" preference, tech is 40 % in single stocks, and 81.3 % is US-listed against a mixed
   CAD/USD preference. Show a visible "Conflits" box; never say "selon vos garde-fous" for a
   scenario that breaches one. The word "persona" leaked into user text.
4. **Spot crypto in a TFSA.** CELI account still offers BTC-USD and ETH-USD. Spot coins are not
   qualified TFSA investments; only listed crypto ETFs are. Exclude them with the reason.
5. **Evaluated asset not taken from the question.** It must come from the question only; news is
   also duplicated in the list.
6. **Buy/sell wording and growth forecasts.** Remove them; extend the verifier's checks.
7. **Budget above CELI room.** Warn when the budget exceeds the CELI room for the age band.

### P1

8. One versioned profile; export every questionnaire field.
9. Plain-language answer: direct verdict, limits crossed and portfolio described in words; in the
   details, allocation and guardrail check first.
10. Minimum line size and maximum number of lines.
11. ETF look-through for sector, country and overlap. *(deferred)*
12. All-in cost tile including the FX cost.
13. Ticker validation, visible "Hors univers" badge, block save above 100 %.

### P2 / P3

14. Longer history via index proxies; survivorship note. *(deferred)*
15. Recalibrate the baseline for high-risk profiles.
16. Translate English strings and JSON; plain-language labels and tooltips.
17. Step counter and time estimate while loading; show results progressively.
18. Evidence popovers; what-if side by side; better history entries.
19. Section numbers, truncated labels, aria labels, "(détail)" link text.

## Acceptance test suggested by the report

Replay the three questions and assert that (a) the requested assets appear in "as requested",
(b) SOL appears as "Non analysé" at 40 %, (c) the 25 % loss breach is flagged, and (d) no spot
crypto appears for a CELI.
