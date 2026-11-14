# Sources — ETF holdings

## Dataset
- File: `data/etf/fund_holdings.csv`
- Columns: `etf, holding_ticker, holding_name, weight, as_of_date, source_url, retrieved_date`
- Weight is a fraction of fund NAV (top 25 holdings per ETF).
- as_of_date: 2026-11-12 for all (issuer basket date).
- retrieved_date: 2026-11-14
- Coverage: 5 ETFs × 25 holdings = 125 rows: XIU.TO, XBB.TO, AGG, TLT, SPY.

## Retrieved (issuer sites)
- XIU.TO (iShares S&P/TSX 60): BlackRock Canada holdings CSV ajax
  - https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf/1464253357814.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund
- XBB.TO (iShares Core Canadian Universe Bond): BlackRock Canada holdings CSV ajax
  - https://www.blackrock.com/ca/investors/en/products/239493/ishares-canadian-universe-bond-index-etf/1464253357814.ajax?fileType=csv&fileName=XBB_holdings&dataType=fund
- AGG (iShares Core U.S. Aggregate Bond): iShares US latest-holdings.csv
  - https://www.ishares.com/us/products/239458/ishares-core-us-aggregate-bond-etf/latest-holdings.csv
- TLT (iShares 20+ Year Treasury Bond): iShares US latest-holdings.csv
  - https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf/latest-holdings.csv
- SPY (SPDR S&P 500): State Street daily holdings XLSX
  - https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx

## Non récupéré (skipped)
- QQQ (Invesco QQQ Trust): issuer site returned HTTP 406 for automated requests after 2 attempts; not fetched. No holdings invented.
- ESGV (Vanguard ESG U.S. Stock ETF): issuer holdings/PCF not retrievable via simple HTTP after 2 attempts; not fetched.
- ZST.TO (BMO Ultra Short-Term Bond ETF): issuer site unreachable (connection failure) after 2 attempts; not fetched.
- GLD (SPDR Gold Shares): issuer provides no downloadable equity-style holdings file (physical gold bullion); skipped.

## License / terms
- iShares/BlackRock, SPDR/State Street holdings are publicly available fund composition data; used for research with attribution.
- Top-25 truncation means weights do not sum to 1; look-through expands only available holdings.

## Access notes
- Rate: polite single requests; no API rate limits stated for these issuer downloads.
- User-Agent: Mozilla/5.0 for issuer pages.
