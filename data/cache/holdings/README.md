# ETF holdings cache

Cached ETF holdings documents, committed so runs never depend on the network. Loaded by `alphaforge/data/holdings.py`. Used for Mateo's ESG screen (ESGV membership) and for ETF overlap findings.

Holdings are stored as flat files (`<ETF>.json`) and as dated snapshot subdirectories (`<ETF>/<DATE>.json`). When an `as_of_date` is evaluated, the latest snapshot on or before that date is selected.

| File / Directory | As of | Source | Coverage |
|---|---|---|---|
| `SPY.json`, `SPY/` | 2026-11-12 | State Street, SPY daily holdings spreadsheet | full list, 503 names (`complete: true`) |
| `XIU.TO.json`, `XIU.TO/` | 2026-11-12 | BlackRock iShares Canada, XIU holdings CSV | full list, 60 names (`complete: true`) |
| `QQQ.json`, `QQQ/` | 2026-06-30, 2026-03-31 | SEC EDGAR Form NPORT-P (CIK 0001067839) + OpenFIGI | full list, 101 names (`complete: true`) |
| `ESGV.json`, `ESGV/` | 2026-09-30 | Vanguard public portfolio holdings API | full list, 1206 names (`complete: true`) |

## Format

```json
{"ticker": "SPY", "as_of": "2026-11-12", "source_url": "...", "source_name": "...",
 "retrieved_at": "2026-11-15", "complete": true, "total_holdings": 503,
 "coverage_weight": 0.9987, "holdings": [{"ticker": "AAPL", "name": "APPLE INC", "weight": 0.079044}]}
```

## Processing

- Weights converted to fractions and sorted by weight descending.
- SPY: non-ticker cash/futures rows dropped.
- XIU.TO: only `Asset Class = Equity` rows kept; TSX tickers suffixed with `.TO` to match `assets_universe.csv` (`RY` becomes `RY.TO`).
- QQQ: extracted from official SEC EDGAR Form NPORT-P filings with CUSIP mapping via OpenFIGI and verified against the Nasdaq-100 composition. All equity constituents included with `complete: true`.
- ESGV: extracted directly from Vanguard's public API endpoint with 1,206 holdings and market values converted to fractions, with `complete: true`.

## Dated snapshots

Holdings snapshots are organized in `data/cache/holdings/<ETF>/<DATE>.json`.
`load_holdings(etf, as_of=...)` picks the latest snapshot at or before `as_of`. If `as_of` is earlier than all available snapshots, it falls back to the earliest snapshot and the quant node logs an assumption noting that future holdings were used.
