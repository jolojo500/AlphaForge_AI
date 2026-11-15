# Long index history (proxies for drawdown and stress before 2021)

The price files only start on 2021-11-12, so the drawdown and the 2022 stress of a scenario
see one rate-hike episode and no bear market. `index_monthly.csv` gives each scenario a
companion computed on long index proxies that cover 2000-02 and 2008 (#176). Loaded by
`alphaforge/data/index_history.py`; the code reads this committed file and never downloads.

| Column | Ticker | What | Currency | Coverage |
|---|---|---|---|---|
| `GSPC` | `^GSPC` | S&P 500 price index (no dividends) | USD | 1999-01-31 .. 2026-10-31 |
| `GSPTSE` | `^GSPTSE` | S&P/TSX Composite price index (no dividends) | CAD | 1999-01-31 .. 2026-10-31 |
| `AGG` | `AGG` | iShares Core U.S. Aggregate Bond ETF, adjusted close (distributions reinvested) | USD | 2003-09-30 .. 2026-10-31 (fund inception; **gap before**, the bond sleeve is held flat) |

- Source: Yahoo Finance via `yfinance` 1.8.0, `yf.download(ticker, start="1999-01-01", interval="1mo", auto_adjust=True)`, `Close`.
  Source URLs: https://finance.yahoo.com/quote/%5EGSPC/history/, https://finance.yahoo.com/quote/%5EGSPTSE/history/, https://finance.yahoo.com/quote/AGG/history/
- Retrieved: 2026-11-15. The partial month 2026-11 was dropped; the last row is the October 2026 close.
- Rows are dated at month end (the date on which the monthly close is observed), so an as-of
  filter `date <= as_of_date` never reads a close that was not yet known.
- Local currency, no FX conversion: S&P 500 and AGG in USD, S&P/TSX in CAD. Price indexes
  understate total return, so their drawdowns are slightly worse than a total-return index.
- 334 rows, 3 columns, values rounded to 4 decimals.
