"""SQLite database persistence for custom/dynamically ingested market assets and prices.

Track A & Dynamic Asset Discovery:
Assets fetched via yfinance or external sources are persisted into a local SQLite database
(data/market.db), ensuring they are never re-queried from external APIs on subsequent runs.
"""

from __future__ import annotations

import csv
import logging
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from alphaforge import config

logger = logging.getLogger(__name__)

DB_PATH = Path(config.REPO_ROOT) / "data" / "market.db"


def get_db_path() -> Path:
    db_file = Path(getattr(config, "MARKET_DB_PATH", DB_PATH))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    return db_file


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_market_db() -> None:
    """Initialize the SQLite market database tables if not existing."""
    conn = _get_connection()
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_assets (
                ticker TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                asset_class TEXT NOT NULL,
                market TEXT,
                currency TEXT NOT NULL,
                sector TEXT,
                source TEXT DEFAULT 'yfinance',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_prices (
                date TEXT,
                ticker TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume REAL,
                currency TEXT,
                PRIMARY KEY (ticker, date)
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prices_ticker ON custom_prices(ticker)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prices_date ON custom_prices(date)")
    finally:
        conn.close()


# Ensure tables are created on module import
init_market_db()


def get_custom_assets_df(tickers: list[str] | set[str] | None = None) -> pd.DataFrame:
    """Retrieve dynamically ingested assets as a pandas DataFrame."""
    conn = _get_connection()
    try:
        if tickers is not None:
            t_list = [str(t).strip().upper() for t in tickers]
            if not t_list:
                return pd.DataFrame(columns=["asset_id", "ticker", "name", "asset_class", "market", "currency", "sector"])
            placeholders = ",".join("?" for _ in t_list)
            query = f"SELECT ticker, name, asset_class, market, currency, sector FROM custom_assets WHERE ticker IN ({placeholders})"
            df = pd.read_sql(query, conn, params=t_list)
        else:
            df = pd.read_sql(
                "SELECT ticker, name, asset_class, market, currency, sector FROM custom_assets",
                conn,
            )
        if not df.empty:
            df["asset_id"] = "DYN_" + df["ticker"]
        return df
    except Exception as e:
        logger.warning("Error reading custom_assets from DB: %s", e)
        return pd.DataFrame(columns=["asset_id", "ticker", "name", "asset_class", "market", "currency", "sector"])
    finally:
        conn.close()


def get_custom_prices_df(tickers: list[str] | set[str] | None = None) -> pd.DataFrame:
    """Retrieve historical daily prices for custom assets as a pandas DataFrame."""
    conn = _get_connection()
    try:
        cols = "date, ticker, open, high, low, close, adj_close, volume, currency"
        if tickers is not None:
            t_list = list(tickers)
            if not t_list:
                return pd.DataFrame(columns=cols.replace(" ", "").split(","))
            placeholders = ",".join("?" for _ in t_list)
            query = f"SELECT {cols} FROM custom_prices WHERE ticker IN ({placeholders})"
            df = pd.read_sql(query, conn, params=t_list)
        else:
            df = pd.read_sql(f"SELECT {cols} FROM custom_prices", conn)

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        logger.warning("Error reading custom_prices from DB: %s", e)
        return pd.DataFrame(columns=cols.replace(" ", "").split(","))
    finally:
        conn.close()


def has_custom_asset(ticker: str) -> bool:
    """Check if an asset is already persisted in the database."""
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM custom_assets WHERE ticker = ? LIMIT 1", (ticker.strip().upper(),))
        return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        conn.close()


def save_custom_asset(asset_dict: dict[str, Any], prices_records: list[dict[str, Any]]) -> None:
    """Persist an asset and its price history into the database."""
    conn = _get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO custom_assets (ticker, name, asset_class, market, currency, sector, source)
                VALUES (:ticker, :name, :asset_class, :market, :currency, :sector, :source)
                """,
                {
                    "ticker": asset_dict["ticker"],
                    "name": asset_dict["name"],
                    "asset_class": asset_dict["asset_class"],
                    "market": asset_dict.get("market", "Unknown"),
                    "currency": asset_dict.get("currency", "USD"),
                    "sector": asset_dict.get("sector", "Other"),
                    "source": asset_dict.get("source", "yfinance"),
                },
            )
            if prices_records:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO custom_prices (date, ticker, open, high, low, close, adj_close, volume, currency)
                    VALUES (:date, :ticker, :open, :high, :low, :close, :adj_close, :volume, :currency)
                    """,
                    prices_records,
                )
        logger.info("Saved %d price rows for custom asset %s in DB", len(prices_records), asset_dict["ticker"])
    except Exception as e:
        logger.error("Failed to save custom asset %s: %s", asset_dict.get("ticker"), e)
        raise
    finally:
        conn.close()


def get_merged_universe_dict() -> dict[str, dict[str, Any]]:
    """Return universe dict mapping ticker -> row dict (starter CSV 31 assets + DB custom assets)."""
    out: dict[str, dict[str, Any]] = {}
    csv_file = config.STARTER_DIR / "assets_universe.csv"
    if csv_file.exists():
        with open(csv_file, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["ticker"]] = dict(r)

    # Merge custom assets from SQLite
    custom_df = get_custom_assets_df()
    for _, row in custom_df.iterrows():
        out[row["ticker"]] = row.to_dict()

    return out
