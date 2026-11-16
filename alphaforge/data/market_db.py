"""SQLite cache of the dynamically ingested market assets and prices, backed by S3.

Assets fetched via yfinance are persisted in a local SQLite database (``data/market.db``)
so they are never re-queried from Yahoo Finance in the same container. That file is lost
at every redeploy, so when ``config.S3_BUCKET`` is set each ingested asset is also written
through to S3 as ``cache/ingested/<TICKER>.json`` (metadata + price records); the same
document is mirrored under ``data/cache/ingested/`` locally, which is exactly what
``infra.sync_s3.pull_caches`` restores at startup. On first access the documents that are
not yet in SQLite are loaded back.

User profiles never live here: they belong to the users store (``alphaforge.users``).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from alphaforge import config

logger = logging.getLogger(__name__)

DB_PATH = Path(config.REPO_ROOT) / "data" / "market.db"
INGESTION_ENV = "AF_DYNAMIC_INGESTION"
INGESTED_PREFIX = "cache/ingested"  # S3 key prefix, mirrored under config.CACHE_DIR / "ingested"


def ingestion_enabled() -> bool:
    """Dynamic ingestion switch (``AF_DYNAMIC_INGESTION``, default "off").

    When off, the ingested assets of the local DB are invisible too: every run sees exactly
    the curated universe, as on main, and an asset outside it stays "Non analysé".
    """
    return os.getenv(INGESTION_ENV, "off").strip().lower() in ("1", "on", "true", "yes")


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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                retrieved_at TEXT
            )
            """)
            # Databases created before the column existed (the date of the download is cited).
            cols = {r[1] for r in conn.execute("PRAGMA table_info(custom_assets)").fetchall()}
            if "retrieved_at" not in cols:
                conn.execute("ALTER TABLE custom_assets ADD COLUMN retrieved_at TEXT")
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
            # Profiles live in the users store only (#192); an older local file may carry the table.
            conn.execute("DROP TABLE IF EXISTS user_profiles")
    finally:
        conn.close()


# Ensure tables are created on module import
init_market_db()


CUSTOM_ASSET_COLUMNS = [
    "asset_id", "ticker", "name", "asset_class", "market", "currency", "sector", "source", "retrieved_at",
]
_SELECT_ASSETS = (
    "SELECT ticker, name, asset_class, market, currency, sector, source, "
    "COALESCE(retrieved_at, created_at) AS retrieved_at FROM custom_assets"
)


def get_custom_assets_df(tickers: list[str] | set[str] | None = None) -> pd.DataFrame:
    """Retrieve dynamically ingested assets as a pandas DataFrame.

    `asset_id` is "DYN_<ticker>" (so every node can tell an ingested asset from a curated
    one), `source` and `retrieved_at` say where and when the data was downloaded.
    """
    if not ingestion_enabled():
        return pd.DataFrame(columns=CUSTOM_ASSET_COLUMNS)
    _ensure_cache_loaded()
    conn = _get_connection()
    try:
        if tickers is not None:
            t_list = [str(t).strip().upper() for t in tickers]
            if not t_list:
                return pd.DataFrame(columns=CUSTOM_ASSET_COLUMNS)
            placeholders = ",".join("?" for _ in t_list)
            df = pd.read_sql(f"{_SELECT_ASSETS} WHERE ticker IN ({placeholders})", conn, params=t_list)
        else:
            df = pd.read_sql(_SELECT_ASSETS, conn)
        if not df.empty:
            df["asset_id"] = "DYN_" + df["ticker"]
            df["sector"] = df["sector"].fillna("Inconnu")
        return df
    except Exception as e:
        logger.warning("Error reading custom_assets from DB: %s", e)
        return pd.DataFrame(columns=CUSTOM_ASSET_COLUMNS)
    finally:
        conn.close()


def get_custom_prices_df(tickers: list[str] | set[str] | None = None) -> pd.DataFrame:
    """Retrieve historical daily prices for custom assets as a pandas DataFrame."""
    cols = "date, ticker, open, high, low, close, adj_close, volume, currency"
    if not ingestion_enabled():
        return pd.DataFrame(columns=cols.replace(" ", "").split(","))
    _ensure_cache_loaded()
    conn = _get_connection()
    try:
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
    """Check if an asset is already persisted in the database (always False when ingestion is off)."""
    if not ingestion_enabled():
        return False
    _ensure_cache_loaded()
    return _has_asset_row(ticker)


def _has_asset_row(ticker: str) -> bool:
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM custom_assets WHERE ticker = ? LIMIT 1", (ticker.strip().upper(),))
        return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        conn.close()


# --- S3 write-through and reload (the SQLite file does not survive a redeploy) ------------

_s3_client_override: Any = None
_cache_loaded_for: set[str] = set()


def set_s3_client(client: Any) -> None:
    """Inject an S3 client (tests use a stub); None restores the boto3 client."""
    global _s3_client_override
    _s3_client_override = client


def s3_bucket() -> str | None:
    return getattr(config, "S3_BUCKET", None) or os.getenv("AF_S3_BUCKET") or None


def _s3_client() -> Any:
    if _s3_client_override is not None:
        return _s3_client_override
    if not s3_bucket():
        return None
    import boto3  # lazy: never needed without a bucket

    region = os.getenv("AWS_REGION", "us-east-1")
    profile = os.getenv("AWS_PROFILE")
    session = boto3.Session(profile_name=profile, region_name=region) if profile else boto3.Session(region_name=region)
    return session.client("s3", region_name=region)


def ingested_cache_dir() -> Path:
    """Local mirror of s3://<bucket>/cache/ingested/, synced by infra.sync_s3 (push_all / pull_caches)."""
    return Path(config.CACHE_DIR) / "ingested"


def ingested_key(ticker: str) -> str:
    return f"{INGESTED_PREFIX}/{ticker.strip().upper()}.json"


def _write_through(asset_dict: dict[str, Any], prices_records: list[dict[str, Any]]) -> None:
    """Mirror the ingested asset as JSON locally and, with a bucket, in S3. Never raises."""
    ticker = str(asset_dict["ticker"]).strip().upper()
    doc = {"asset": {**asset_dict, "ticker": ticker}, "prices": prices_records}
    payload = json.dumps(doc, ensure_ascii=False, default=str)
    try:
        d = ingested_cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{ticker}.json").write_text(payload, encoding="utf-8")
    except Exception:
        logger.exception("Could not mirror ingested asset %s under %s", ticker, ingested_cache_dir())
    bucket = s3_bucket()
    if not bucket:
        return
    try:
        client = _s3_client()
        if client is None:
            return
        client.put_object(
            Bucket=bucket,
            Key=ingested_key(ticker),
            Body=payload.encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Ingested asset %s written through to s3://%s/%s", ticker, bucket, ingested_key(ticker))
    except Exception:
        logger.exception("Could not write ingested asset %s to S3 bucket %s", ticker, bucket)


def load_ingested_from_cache(cache_dir: Path | str | None = None) -> list[str]:
    """Insert into SQLite every ``cache/ingested/*.json`` (as pulled by ``pull_caches``) that is
    not there yet. Returns the tickers loaded. Never raises."""
    d = Path(cache_dir) if cache_dir is not None else ingested_cache_dir()
    loaded: list[str] = []
    if not d.is_dir():
        return loaded
    for f in sorted(d.glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
            asset = dict(doc["asset"])
            ticker = str(asset.get("ticker") or f.stem).strip().upper()
            asset["ticker"] = ticker
            if _has_asset_row(ticker):
                continue
            save_custom_asset(asset, list(doc.get("prices") or []), write_through=False)
            loaded.append(ticker)
        except Exception:
            logger.exception("Skipping unreadable ingested cache file %s", f)
    if loaded:
        logger.info("Loaded %d ingested asset(s) from %s: %s", len(loaded), d, ", ".join(loaded))
    return loaded


def _ensure_cache_loaded() -> None:
    """First access per database file: reload the pulled cache documents (lazy, once)."""
    key = str(get_db_path())
    if key in _cache_loaded_for:
        return
    _cache_loaded_for.add(key)
    load_ingested_from_cache()


def save_custom_asset(
    asset_dict: dict[str, Any], prices_records: list[dict[str, Any]], *, write_through: bool = True
) -> None:
    """Persist an asset and its price history into the database, and mirror it to S3."""
    conn = _get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO custom_assets
                    (ticker, name, asset_class, market, currency, sector, source, retrieved_at)
                VALUES (:ticker, :name, :asset_class, :market, :currency, :sector, :source, :retrieved_at)
                """,
                {
                    "ticker": asset_dict["ticker"],
                    "name": asset_dict["name"],
                    "asset_class": asset_dict["asset_class"],
                    "market": asset_dict.get("market") or "Inconnu",
                    "currency": asset_dict.get("currency", "USD"),
                    "sector": asset_dict.get("sector") or "Inconnu",
                    "source": asset_dict.get("source", "yfinance"),
                    "retrieved_at": asset_dict.get("retrieved_at")
                    or dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S"),
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
    if write_through:
        _write_through(asset_dict, prices_records)


def get_merged_universe_dict() -> dict[str, dict[str, Any]]:
    """Ticker -> row dict of the curated universe, plus the DB assets when ingestion is on."""
    out: dict[str, dict[str, Any]] = {}
    csv_file = config.STARTER_DIR / "assets_universe.csv"
    if csv_file.exists():
        with open(csv_file, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["ticker"]] = dict(r)

    # Merge custom assets from SQLite (empty when ingestion is off)
    custom_df = get_custom_assets_df()
    for _, row in custom_df.iterrows():
        out[row["ticker"]] = row.to_dict()

    return out

