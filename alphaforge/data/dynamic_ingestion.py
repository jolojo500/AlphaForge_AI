"""Dynamic asset ingestion service via yfinance and SQLite persistence.

When a user query names an asset outside the starter 31-asset universe (e.g. "dogecoin", "PLTR",
"Solana"), this module:
1. Checks if it is already persisted in the local SQLite database (`data/market.db`).
   If present, loads it from the DB immediately (zero external network call).
2. If absent from DB, resolves the ticker via known alias or yfinance search.
3. Downloads 5-year historical prices (2021-11-12 to 2026-11-12) and metadata.
4. Persists the asset and its daily prices into `data/market.db`.
5. Returns the resolved ticker so downstream nodes (Profile, Scenarios, Guardrails, Explain)
   treat it as an authentic asset with full quantitative simulation.
"""

from __future__ import annotations

import logging
import re

import pandas as pd

from alphaforge.data.market_db import (
    get_merged_universe_dict,
    has_custom_asset,
    save_custom_asset,
)

logger = logging.getLogger(__name__)

# Canonical aliases for quick resolution without network search
COMMON_ALIASES: dict[str, str] = {
    "dogecoin": "DOGE-USD",
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
}

START_DATE = "2021-11-12"
END_DATE = "2026-11-13"


def resolve_candidate_symbol(text: str) -> str | None:
    """Detect if a user prompt mentions a candidate ticker or asset name."""
    lowered = text.lower()

    # 1. Check known aliases
    for name, sym in sorted(COMMON_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return sym

    # 2. Check explicit uppercase tickers in text (e.g. "PLTR", "SOL-USD", "DOGE")
    tokens = re.findall(r"\b[A-Z]{2,6}(?:-[A-Z]{2,4}|\.[A-Z]{2})?\b", text)
    universe = get_merged_universe_dict()
    for tok in tokens:
        if tok in universe or has_custom_asset(tok):
            return tok
        # If not known but looks like a ticker, return as candidate
        if tok not in {"USD", "CAD", "EUR", "FNB", "ETF", "CEO", "AI", "IA"}:
            return tok

    return None


def fetch_and_persist_asset(symbol: str) -> str | None:
    """Fetch asset metadata and 5-year daily prices via yfinance, and persist to SQLite DB."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance is not installed; cannot ingest dynamic asset %s", symbol)
        return None

    symbol = symbol.strip().upper()
    if has_custom_asset(symbol):
        logger.info("Asset %s is already in DB", symbol)
        return symbol

    logger.info("Fetching dynamic asset %s from yfinance...", symbol)
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}

        # If symbol is invalid or empty
        name = info.get("name") or info.get("shortName") or info.get("longName") or symbol
        quote_type = str(info.get("quoteType", "")).upper()

        if "CRYPTO" in quote_type or "-USD" in symbol or symbol.endswith("-CAD"):
            asset_class = "crypto"
            market = "Crypto"
            sector = "Cryptocurrency"
        elif "ETF" in quote_type:
            asset_class = "etf_equity"
            market = info.get("exchange", "Unknown")
            sector = info.get("category", "Broad market")
        else:
            asset_class = "equity"
            market = info.get("exchange", "Unknown")
            sector = info.get("sector", "Other")

        currency = info.get("currency", "CAD" if symbol.endswith(".TO") else "USD")

        # Download daily history
        df = yf.download(symbol, start=START_DATE, end=END_DATE, progress=False)
        if df is None or df.empty:
            logger.warning("yfinance returned no price history for %s", symbol)
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        # Find date column
        date_col = next((c for c in df.columns if str(c).lower() == "date"), None)
        if not date_col:
            return None

        df["date"] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
        df["ticker"] = symbol
        df["currency"] = currency
        df["open"] = df["Open"].fillna(0.0) if "Open" in df.columns else 0.0
        df["high"] = df["High"].fillna(0.0) if "High" in df.columns else 0.0
        df["low"] = df["Low"].fillna(0.0) if "Low" in df.columns else 0.0
        df["close"] = df["Close"].fillna(0.0) if "Close" in df.columns else 0.0

        if "Adj Close" in df.columns:
            df["adj_close"] = df["Adj Close"].fillna(df["close"])
        else:
            df["adj_close"] = df["close"]

        df["volume"] = df["Volume"].fillna(0.0) if "Volume" in df.columns else 0.0

        records = df[["date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "currency"]].to_dict("records")
        if not records:
            return None

        asset_dict = {
            "ticker": symbol,
            "name": name,
            "asset_class": asset_class,
            "market": market,
            "currency": currency,
            "sector": sector,
            "source": "yfinance",
        }

        save_custom_asset(asset_dict, records)
        logger.info("Successfully ingested and persisted %s into SQLite market.db", symbol)
        return symbol

    except Exception as e:
        logger.warning("Failed to fetch or persist dynamic asset %s: %s", symbol, e)
        return None


def ensure_requested_asset(text: str) -> str | None:
    """Detect if an external asset is asked in text, and ensure it is stored in SQLite DB."""
    cand = resolve_candidate_symbol(text)
    if not cand:
        return None

    cand_upper = cand.strip().upper()
    universe = get_merged_universe_dict()

    # Already in base universe or DB
    if cand_upper in universe or has_custom_asset(cand_upper):
        return cand_upper

    # Need to fetch and persist
    return fetch_and_persist_asset(cand_upper)
