# Sources — Dated news / SEC EDGAR filings

## Dataset
- File: `data/news/news_references.csv`
- Columns: `published_date, ticker, title, form_or_type, url, source, retrieved_date`
- Tickers: TSLA (Tesla, Inc.), NVDA (NVIDIA Corp.)
- Forms: 8-K, 8-K/A, 10-Q (recent filings index from SEC EDGAR submissions API)
- Row count: 234 (TSLA 155, NVDA 79)
- Retrieved date: 2026-11-14

## Source
- SEC EDGAR submissions API: `https://data.sec.gov/submissions/CIK##########.json`
  - TSLA CIK 0001318605: https://data.sec.gov/submissions/CIK0001318605.json
  - NVDA CIK 0001045810: https://data.sec.gov/submissions/CIK0001045810.json
- Filing document URLs: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{primaryDocument}`
- HTTP header `User-Agent: AlphaForge-AI datathon research team-contact@example.com`
- Rate: <= 5 req/s (script slept 0.2s between requests; only 2 API calls).

## License / terms
- SEC EDGAR data is public domain (U.S. government work). Free to use with fair access; User-Agent required.
- Factual filing metadata only; titles derived from form/items fields, no invented headlines.

## Access notes
- No look-ahead: consumers must filter by `published_date <= as_of_date` (see `alphaforge/app/tools/news.py::news_for`).
