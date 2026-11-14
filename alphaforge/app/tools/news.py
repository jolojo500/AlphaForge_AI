"""Dated news / filing references for AlphaForge AI.

Provides look-ahead-safe access to published news and SEC EDGAR filing references.
All dates are publication/filing dates; ``news_for`` filters strictly to items
published on or before ``as_of_date``.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Default locations relative to repository root (alphaforge/app/tools -> parents[3])
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


class NewsFrame(pd.DataFrame):
    """A DataFrame of news references that also behaves like a list of records.

    Iteration and integer indexing yield dict records, which keeps the tool
    convenient for both pandas-style and list-style callers.
    """

    _metadata = ["_records"]

    def __init__(self, *args, **kwargs):
        records = kwargs.pop("_records", None)
        super().__init__(*args, **kwargs)
        if records is None:
            records = self.to_dict("records") if len(self) else []
        self._records = list(records)

    @property
    def _constructor(self):
        return NewsFrame

    def __iter__(self):
        return iter(self._records)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._records[key]
        return super().__getitem__(key)

    def to_records_list(self) -> list[dict[str, Any]]:
        return list(self._records)


def _parse_date(value: Any) -> pd.Timestamp:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).normalize()
    return pd.Timestamp(str(value)).normalize()


def _default_news_path(data_dir: str | Path | None = None) -> Path:
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    return base / "news" / "news_references.csv"


def load_news_references(data_dir: str | Path | None = None) -> pd.DataFrame:
    """Load the news references CSV into a DataFrame."""
    path = _default_news_path(data_dir)
    if not path.exists():
        return pd.DataFrame(
            columns=["published_date", "ticker", "title", "form_or_type", "url", "source", "retrieved_date"]
        )
    df = pd.read_csv(path)
    if "published_date" in df.columns:
        df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


def news_for(
    ticker: str,
    as_of_date: Any,
    data_dir: str | Path | None = None,
) -> NewsFrame:
    """Return news/filing references for ``ticker`` published on or before ``as_of_date``.

    No look-ahead: items with ``published_date > as_of_date`` are excluded.
    """
    df = load_news_references(data_dir)
    if df.empty:
        return NewsFrame(df)

    cutoff = _parse_date(as_of_date).strftime("%Y-%m-%d")
    mask = df["ticker"].astype(str).str.upper() == str(ticker).upper()
    if "published_date" in df.columns:
        mask = mask & (df["published_date"].astype(str) <= cutoff)
    out = df.loc[mask].copy()
    if "published_date" in out.columns:
        out = out.sort_values("published_date", ascending=True, kind="stable")
    out = out.reset_index(drop=True)
    return NewsFrame(out)


__all__ = ["news_for", "load_news_references", "NewsFrame"]
