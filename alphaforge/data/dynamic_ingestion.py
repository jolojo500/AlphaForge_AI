"""Dynamic asset ingestion via yfinance and SQLite persistence (opt-in, off by default).

When a question names a security outside the curated universe ("l'action PLTR", "$DOGE",
"dogecoin"), this module can download its history from Yahoo Finance and persist it in
`data/market.db` so later runs read it locally. Rules:

- It runs only when the environment variable ``AF_DYNAMIC_INGESTION`` is "on" (default
  "off"; the test suite forces "off"). When off, or on any failure, nothing is downloaded
  and the asset stays outside the universe, listed "Non analysé" exactly as before.
- A token is a candidate only when the text marks it as a security ("l'action XYZ",
  "le titre XYZ", "l'ETF XYZ", "le FNB XYZ", "ticker XYZ", "symbole XYZ", "stock XYZ",
  "shares of XYZ", "$XYZ") or when it is in the alias table. Finance acronyms (ESG, CELI,
  REER, FNB, TSX, USD...) are never candidates. A ticker of the curated universe is never
  overridden.
- Every download runs in a worker thread with a hard timeout (``AF_YF_TIMEOUT_S``, default
  20 s) and every exception is caught.
- An ingested asset carries ``asset_class`` / ``market`` / ``currency`` / ``sector`` read
  from Yahoo Finance (sector "Inconnu" when missing) so screening, caps and guardrails
  apply the same rules to it; the evidence says it was downloaded and is outside the
  curated universe.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
import os
import re

import pandas as pd

from alphaforge.data.market_db import (
    INGESTION_ENV,
    get_merged_universe_dict,
    has_custom_asset,
    ingestion_enabled,
    save_custom_asset,
)

logger = logging.getLogger(__name__)

UNKNOWN_SECTOR = "Inconnu"

# Canonical aliases for quick resolution without network search
COMMON_ALIASES: dict[str, str] = {
    "dogecoin": "DOGE-USD",
    "dogercoin": "DOGE-USD",
    "dodgecoin": "DOGE-USD",
    "doge-coin": "DOGE-USD",
    "doge": "DOGE-USD",
    "solana": "SOL-USD",
    "sol": "SOL-USD",
    "ripple": "XRP-USD",
    "xrp": "XRP-USD",
    "cardano": "ADA-USD",
    "ada": "ADA-USD",
    "polkadot": "DOT-USD",
    "dot": "DOT-USD",
    "avalanche": "AVAX-USD",
    "avax": "AVAX-USD",
    "shiba": "SHIB-USD",
    "shib": "SHIB-USD",
    "shiba inu": "SHIB-USD",
    "binance": "BNB-USD",
    "bnb": "BNB-USD",
    "palantir": "PLTR",
    "meta": "META",
    "uber": "UBER",
    "coinbase": "COIN",
    "microstrategy": "MSTR",
    "amd": "AMD",
    "netflix": "NFLX",
    "sofi": "SOFI",
    "tsmc": "TSM",
    "taiwan semiconductor": "TSM",
    "taiwan semi": "TSM",
}

# Finance / French acronyms that look like tickers but never are (unless in the universe).
STOP_TOKENS: frozenset[str] = frozenset({
    "ESG", "CELI", "REER", "CELIAPP", "CRI", "FERR", "FNB", "ETF", "TSX", "USD", "CAD",
    "EUR", "RRSP", "TFSA", "FHSA", "HHI", "PEA", "IPO", "GICS", "S&P", "SP", "BTC", "ETH",
    "CEO", "AI", "IA", "MER", "REIT", "FPI", "ARC", "CRA", "GIC", "CPG", "RRQ", "CPP",
    "RRIF", "LIRA", "LIF", "FRV", "OPC", "FCP", "YTD", "ROI", "ROE", "EPS", "PE", "AMF",
    "OSC", "SEC", "NYSE", "NASDAQ", "DCA", "KYC", "AUM", "NAV", "GPT", "LLM",
    "EQUITY", "BOND", "GOLD", "CRYPTO",
})

_TOKEN = r"([A-Za-z][A-Za-z0-9]{0,5}(?:[-.][A-Za-z]{1,4})?)"
_MARKED_RE = re.compile(
    r"(?:l['’]action|le titre|l['’]etf|le fnb|ticker|symbole|stock|shares of)"
    r"\s*(?:de\s+|du\s+|d['’]|:\s*)?\$?" + _TOKEN + r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_DOLLAR_RE = re.compile(r"\$" + _TOKEN + r"(?![A-Za-z0-9])")

START_DATE = "2021-11-12"
END_DATE = "2026-11-13"


# --- switches -----------------------------------------------------------------------------


def yf_timeout_s() -> float:
    try:
        return max(0.05, float(os.getenv("AF_YF_TIMEOUT_S", "20")))
    except ValueError:
        return 20.0


def is_stop_token(token: str) -> bool:
    return token.strip().upper() in STOP_TOKENS


# --- candidate detection ------------------------------------------------------------------


def _universe_ticker(token: str, universe: dict) -> str | None:
    """The curated/DB ticker a token designates ("SHOP" -> "SHOP.TO"), else None."""
    key = token.strip().upper()
    for t in universe:
        if key in (t.upper(), t.upper().split(".")[0]):
            return t
    return None


def _alias_in_text(text: str, lowered: str) -> str | None:
    """An alias written in full (dogecoin, palantir) anywhere; a short alias (sol, meta,
    doge) only when written in capitals, so French words never become tickers."""
    for name, sym in sorted(COMMON_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        short = name.isalpha() and len(name) <= 4
        if short:
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(name.upper())}(?![A-Za-z0-9])", text):
                return sym
        elif re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", lowered):
            return sym
    return None


def resolve_candidate_symbol(text: str) -> str | None:
    """The security the text explicitly names, or None.

    Order: a ticker of the curated universe or of the DB (never overridden), a known
    alias, then a token marked as a security ("l'action XYZ", "$XYZ") that is not a
    finance acronym. A bare capitalised word (ESG, CELI, TSX) is never a candidate.
    """
    if not text or not text.strip():
        return None
    lowered = text.lower()
    universe = get_merged_universe_dict()

    marked = [m.group(1) for m in _MARKED_RE.finditer(text)] + [m.group(1) for m in _DOLLAR_RE.finditer(text)]
    for tok in marked:
        known = _universe_ticker(tok, universe)
        if known:
            return known

    alias = _alias_in_text(text, lowered)
    if alias:
        return alias

    for tok in marked:
        up = tok.upper()
        if is_stop_token(up):
            continue
        if tok.lower() in COMMON_ALIASES:
            return COMMON_ALIASES[tok.lower()]
        return up
    return None


# --- download ------------------------------------------------------------------------------


def _infer_asset_class(quote_type: str, name: str, symbol: str) -> str:
    qt = quote_type.upper()
    low = f"{name} {symbol}".lower()
    if "CRYPTO" in qt or symbol.endswith(("-USD", "-CAD")):
        return "crypto"
    if "ETF" in qt or "FUND" in qt:
        if re.search(r"\b(?:bond|bonds|obligation|obligations|treasury|fixed income|revenu fixe)\b", low):
            return "etf_bond"
        return "etf_equity"
    return "equity"


_EXCHANGES = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NAS": "NASDAQ", "NASDAQ": "NASDAQ",
    "NYQ": "NYSE", "NYSE": "NYSE", "PCX": "NYSE Arca", "ARCA": "NYSE Arca", "BTS": "Cboe BZX",
    "TOR": "TSX", "TSX": "TSX", "TSE": "TSX", "VAN": "TSXV", "CCC": "Crypto (24/7)",
}


def _download_asset(symbol: str) -> tuple[dict, list[dict]] | None:
    """Metadata and daily prices from yfinance (runs in a worker thread; may raise)."""
    import yfinance as yf

    t = yf.Ticker(symbol)
    info = t.info or {}
    name = info.get("name") or info.get("shortName") or info.get("longName") or symbol
    quote_type = str(info.get("quoteType", "")).upper()
    asset_class = _infer_asset_class(quote_type, str(name), symbol)
    if asset_class == "crypto":
        market = "Crypto (24/7)"
        sector = "Crypto asset"
    else:
        raw_ex = str(info.get("exchange") or "").upper()
        market = _EXCHANGES.get(raw_ex) or (raw_ex or "Inconnu")
        if asset_class.startswith("etf"):
            sector = info.get("category") or UNKNOWN_SECTOR
        else:
            sector = info.get("sector") or UNKNOWN_SECTOR
    currency = info.get("currency") or ("CAD" if symbol.endswith((".TO", ".V")) else "USD")

    df = yf.download(symbol, start=START_DATE, end=END_DATE, progress=False)
    if df is None or df.empty:
        logger.warning("yfinance returned no price history for %s", symbol)
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    date_col = next((c for c in df.columns if str(c).lower() == "date"), None)
    if not date_col:
        return None
    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
    out["ticker"] = symbol
    out["currency"] = currency
    for col, src in (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close")):
        out[col] = df[src].fillna(0.0).astype(float) if src in df.columns else 0.0
    out["adj_close"] = (
        df["Adj Close"].fillna(df["Close"] if "Close" in df.columns else 0.0).astype(float)
        if "Adj Close" in df.columns
        else out["close"]
    )
    out["volume"] = df["Volume"].fillna(0.0).astype(float) if "Volume" in df.columns else 0.0
    records = out[["date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "currency"]].to_dict("records")
    if not records:
        return None
    asset = {
        "ticker": symbol,
        "name": str(name),
        "asset_class": asset_class,
        "market": market,
        "currency": str(currency),
        "sector": str(sector),
        "source": "yfinance",
        "retrieved_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S"),
    }
    return asset, records


def fetch_and_persist_asset(symbol: str) -> str | None:
    """Download `symbol` from Yahoo Finance (hard timeout) and persist it; None on any failure.

    Never raises and never touches the network when ingestion is off.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol or is_stop_token(symbol):
        return None
    if has_custom_asset(symbol):
        return symbol
    if not ingestion_enabled():
        logger.info("Dynamic ingestion is off (%s): %s stays outside the universe", INGESTION_ENV, symbol)
        return None
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="af-yf")
    try:
        future = executor.submit(_download_asset, symbol)
        result = future.result(timeout=yf_timeout_s())
        if result is None:
            return None
        asset, records = result
        save_custom_asset(asset, records)
        logger.info("Ingested %s (%d rows) into market.db", symbol, len(records))
        return symbol
    except concurrent.futures.TimeoutError:
        logger.warning("yfinance timed out after %.1fs for %s", yf_timeout_s(), symbol)
        return None
    except Exception as e:  # noqa: BLE001 - any failure leaves the asset outside the universe
        logger.warning("Failed to fetch or persist dynamic asset %s: %s", symbol, e)
        return None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def ensure_requested_asset(text: str) -> str | None:
    """Ticker of the security the text names when it is (or becomes) available locally."""
    if not ingestion_enabled():
        return None
    try:
        cand = resolve_candidate_symbol(text)
    except Exception as e:  # noqa: BLE001
        logger.warning("candidate detection failed: %s", e)
        return None
    if not cand:
        return None
    return ensure_ticker_in_db(cand)


def ensure_ticker_in_db(ticker: str) -> str | None:
    """The ticker when it is in the curated universe or in the DB (after an optional
    download when ingestion is on); None otherwise, so the asset stays "Non analysé"."""
    if not ticker:
        return None
    cleaned = ticker.strip()
    sym = (COMMON_ALIASES.get(cleaned.lower()) or cleaned).upper()
    if is_stop_token(sym):
        return None
    universe = get_merged_universe_dict()
    if sym in universe:
        return sym
    return fetch_and_persist_asset(sym)
