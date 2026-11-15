# ETF holdings cache

One JSON file per ETF, fetched once on 2026-11-14 and committed so runs never depend on the network. Loaded by `alphaforge/data/holdings.py`. Used for Mateo's ESG screen (ESGV membership) and for the ETF overlap finding (the workshop's XSP vs ZEQT example).

| File | As of | Source | Coverage |
|---|---|---|---|
| `SPY.json` | 2026-11-12 | State Street, SPY daily holdings spreadsheet | full list, 503 names |
| `XIU.TO.json` | 2026-11-12 | BlackRock iShares Canada, XIU holdings CSV | full list, 60 names |
| `QQQ.json` | 2026-11-13 | stockanalysis.com QQQ holdings page | top 25 of 104 (71.3% of the fund) |
| `ESGV.json` | 2026-09-30 | stockanalysis.com ESGV holdings page | top 25 of 1220 (55.9% of the fund) |

## Format

```json
{"ticker": "SPY", "as_of": "2026-11-12", "source_url": "...", "source_name": "...",
 "retrieved_at": "2026-11-14", "complete": true, "total_holdings": 503,
 "coverage_weight": 0.9987, "holdings": [{"ticker": "AAPL", "name": "APPLE INC", "weight": 0.079044}]}
```

## Processing

- Weights converted from percent to fractions and sorted by weight. Rows with zero weight dropped.
- SPY: rows without a ticker (cash, futures) dropped.
- XIU.TO: only `Asset Class = Equity` rows kept; TSX tickers suffixed with `.TO` to match `assets_universe.csv` (`RY` becomes `RY.TO`).
- QQQ and ESGV: the issuers' download files could not be fetched from a script, so only the top 25 rows that the public page shows are cached, with `complete: false`.

## Limits

- **Partial lists.** For QQQ and ESGV, a name missing from the file is unknown, not absent. `is_held()` returns `None` in that case, and screening does not exclude a stock for it. Overlaps involving QQQ or ESGV are lower bounds.
- **ESGV and XOM / JNJ.** Neither is in ESGV's top 25, so membership cannot be verified from this file. XOM is excluded for Mateo by the energy-sector rule anyway. JNJ stays eligible, and an assumption entry says why.
- **One snapshot, not point-in-time.** Holdings are as of late 2026. When the analysis date is earlier, the quant node records an assumption saying the overlap at that date may have differed.

To upgrade a partial list, download the issuer's full holdings file in a browser (Vanguard "Export" for ESGV, Invesco "Download holdings" for QQQ), convert it to this format with `complete: true`, and replace the file.
