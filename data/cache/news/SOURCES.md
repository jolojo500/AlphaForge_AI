# News cache sources

`data/cache/news/` holds every news item the news agent can read in `AF_NEWS_MODE=cache` (default).
File name: `<provider>_<TICKER>.json` (company news) or `search_<hash>.json` (web search).

| File | Provider | Content | Limits |
|---|---|---|---|
| `sec_edgar_TSLA.json`, `sec_edgar_NVDA.json` | SEC EDGAR submissions API (public domain), retrieved 2026-11-14 | Filing references (8-K, 8-K/A, 10-Q) from 2024-01-01 | `published_at` is the filing date (publication date). The headline is derived from the form type and item numbers using the SEC item definitions. The filing text was not read. |

Finnhub and Tavily items are added here automatically when the agent runs with `AF_NEWS_MODE=live`
and `FINNHUB_API_KEY` / `TAVILY_API_KEY` set. No item dated after the as-of date is ever used.
