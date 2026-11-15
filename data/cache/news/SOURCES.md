# News cache sources

`data/cache/news/` holds every item the news agent reads in `AF_NEWS_MODE=cache` (the default).
File name: `<provider>_<TICKER>.json` (company news) or `search_<hash>.json` (web search).

| File | Provider | Content | Limits |
|---|---|---|---|
| `sec_edgar_TSLA.json`, `sec_edgar_NVDA.json`, `sec_edgar_XOM.json`, `sec_edgar_ENB.TO.json` | SEC EDGAR submissions API (U.S. public domain), retrieved 2026-11-15 | Filing references since 2025-01-01: 8-K items, 10-Q, 10-K, proxy material (DEF 14A, DEFA14A), shareholder exempt solicitations (PX14A6G), specialized disclosures (SD), prospectus supplements (424B) | `published_at` is the filing date. Headlines come from the form type and the SEC 8-K item definitions; the filing text is not read. Insider and ownership forms are skipped. |
| `sec_edgar_BTC-USD.json` | Same, iShares Bitcoin Trust (IBIT, CIK 1980994) | 10-Q, 10-K and 8-K of a spot bitcoin ETF, used as the dated filing source for bitcoin | An issuer's filings, not news about bitcoin itself. |

Rebuild: `uv run python -m alphaforge.tools.news` (set `AF_EDGAR_USER_AGENT` to a contact address, as the SEC asks).
Finnhub and Tavily items are added automatically when the agent runs with `AF_NEWS_MODE=live` and
`FINNHUB_API_KEY` / `TAVILY_API_KEY` set. No item dated after the as-of date is ever used.
Gap: without those keys the cache has no press coverage, so ESG controversies for Mateo are limited
to shareholder campaigns and specialized disclosures found in filings.
