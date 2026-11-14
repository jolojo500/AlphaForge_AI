# ESG Sources (Issue #4)

Retrieved date for all fetches in this work: **2026-11-14**.

This folder documents public sources used to build `data/esg/esg_flags.csv` for the Datathon universe. Only facts actually fetched from the URLs below were written to the CSV. Where company-specific evidence was not fetched/verified, rows are marked `status=non_verifie`.

## 1. Methodology / index exclusions (ESGV reference)

- **Source:** FTSE Russell, *FTSE Global Choice Index Series Ground Rules v5.0* (PDF)
  - **URL:** https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf
  - **Date/version on document:** August 2026 (v5.0)
  - **Retrieved:** 2026-11-14
  - **License/terms note:** Copyright © 2026 London Stock Exchange Group plc and applicable group undertakings. Document disclaimer states information is provided for information purposes only and restricts reproduction without prior written permission/licensing as applicable (see PDF disclaimer, p. 30). Used here as a factual reference to exclusion categories.
  - **Method used:** Downloaded PDF and extracted text with `pdfplumber` (local) to identify relevant product-related exclusions (Appendix A, pp. 22-24) including oil & gas production/processing/transportation/storage, pipelines, oil sands extraction, and other screened activities used by FTSE Choice indices (including FTSE US All Cap Choice Index tracked by ESGV).

- **Source:** Vanguard, *Vanguard ESG U.S. Stock ETF (ESGV)* product page (advisor site)
  - **URL:** https://advisors.vanguard.com/investments/products/esgv/vanguard-esg-us-stock-etf
  - **Retrieved:** 2026-11-14
  - **License/terms note:** Vanguard website content subject to Vanguard terms of use/copyright; used here as a factual reference.
  - **Method used:** Fetched page HTML/text via `curl` and reviewed embedded product description/metadata stating ESGV seeks to track the performance of a benchmark index measuring U.S. stocks screened for certain environmental, social and corporate governance criteria, with benchmark identified as FTSE US All Cap Choice Index.

## 2. Company business-line facts (public)

> Wikipedia used only for business-line facts as permitted by the task.

- **Source:** Wikipedia, *Canadian Natural Resources*
  - **URL:** https://en.wikipedia.org/wiki/Canadian_Natural_Resources
  - **Retrieved:** 2026-11-14
  - **License/terms note:** Wikipedia content available under CC BY-SA 4.0 (see page footer).
  - **Method used:** Fetched article via web fetch and used business-line facts (e.g., oil and natural gas company; operates Horizon Oil Sands; heavy crude/oil sands operations) to assess fossil-fuel/oil-sands exclusion relevance.

- **Source:** Wikipedia, *Enbridge*
  - **URL:** https://en.wikipedia.org/wiki/Enbridge
  - **Retrieved:** 2026-11-14
  - **License/terms note:** Wikipedia content available under CC BY-SA 4.0 (see page footer).
  - **Method used:** Fetched article via web fetch and used business-line facts (pipeline and energy company transporting crude oil, natural gas, and natural gas liquids) to assess fossil-fuel midstream/pipeline exclusion relevance.

- **Source:** Wikipedia, *ExxonMobil*
  - **URL:** https://en.wikipedia.org/wiki/ExxonMobil
  - **Retrieved:** 2026-11-14
  - **License/terms note:** Wikipedia content available under CC BY-SA 4.0 (see page footer).
  - **Method used:** Fetched article via web fetch and used business-line facts (multinational oil and gas corporation; crude oil/oil products/natural gas) to assess fossil-fuel production exclusion relevance.

## 3. Notes / limitations

- **Scope:** This pass focused on documenting ESGV/FTSE Choice methodology and checking clear fossil-fuel exclusions in the 31-ticker universe using fetched public sources.
- **No invention:** No controversies were invented. Tickers without fetched company-specific exclusion/controversy evidence are marked `non_verifie`.
- **ETFs/bonds/crypto:** Fund holdings-level screening and crypto-asset treatment were not verified with fetched holding-level or crypto-specific exclusion sources in this pass; such rows are marked `non_verifie` where applicable.
