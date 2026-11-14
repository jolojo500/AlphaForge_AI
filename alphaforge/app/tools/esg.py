"""ESG screening utilities for AlphaForge (Mateo persona support).

Pure, offline helpers that load sourced ESG flags and screen tickers.
No network access.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd


DEFAULT_ESG_FLAGS_PATH = Path(__file__).resolve().parents[3] / "data" / "esg" / "esg_flags.csv"

REQUIRED_COLUMNS = [
    "ticker",
    "criterion",
    "status",
    "evidence_text",
    "source_name",
    "source_url",
    "document_page",
    "published_date",
    "retrieved_date",
    "license_note",
]


def _normalize_ticker(ticker: str) -> str:
    return str(ticker).strip().upper()


def _resolve_flags_path(path: str | Path | None = None) -> Path:
    if path is not None:
        p = Path(path)
        if p.exists():
            return p
        raise FileNotFoundError(f"ESG flags file not found: {p}")

    candidates = [
        DEFAULT_ESG_FLAGS_PATH,
        Path("data/esg/esg_flags.csv").resolve(),
        Path.cwd() / "data" / "esg" / "esg_flags.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        "Cannot find ESG flags CSV. Tried: " + ", ".join(str(c) for c in candidates)
    )


def load_esg_flags(path: str | Path | None = None) -> pd.DataFrame:
    """Load ESG flags CSV as a DataFrame.

    Returns a copy with normalized tickers and required columns present.
    """
    flags_path = _resolve_flags_path(path)
    df = pd.read_csv(flags_path, dtype=str).fillna("")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"ESG flags CSV missing required columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()
    df["ticker"] = df["ticker"].map(_normalize_ticker)
    df["status"] = df["status"].str.strip().str.lower()
    return df


def esg_screen(
    tickers: Iterable[str],
    flags_df: pd.DataFrame | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Screen tickers using sourced ESG flags.

    Args:
        tickers: iterable of ticker symbols to screen.
        flags_df: optional pre-loaded flags DataFrame.
        path: optional path to flags CSV if flags_df is not provided.

    Returns:
        {
          "excluded": [tickers with any status == 'exclude'],
          "flagged": [tickers with any status == 'flag' and not excluded],
          "unverified": [tickers with no exclude/flag rows but any status == 'non_verifie',
                         or tickers absent from flags],
          "evidence": [row dicts for requested tickers]
        }
    """
    df = flags_df.copy() if flags_df is not None else load_esg_flags(path)
    if "ticker" not in df.columns or "status" not in df.columns:
        raise ValueError("flags_df must contain at least 'ticker' and 'status' columns")

    df = df.copy()
    df["ticker"] = df["ticker"].map(_normalize_ticker)
    df["status"] = df["status"].astype(str).str.strip().str.lower()

    requested = [_normalize_ticker(t) for t in tickers]
    # preserve order, unique
    seen: set[str] = set()
    ordered: list[str] = []
    for t in requested:
        if t not in seen:
            seen.add(t)
            ordered.append(t)

    subset = df[df["ticker"].isin(seen)].copy()

    excluded: list[str] = []
    flagged: list[str] = []
    unverified: list[str] = []

    for t in ordered:
        rows = subset[subset["ticker"] == t]
        statuses = set(rows["status"].tolist()) if not rows.empty else set()
        if "exclude" in statuses:
            excluded.append(t)
        elif "flag" in statuses:
            flagged.append(t)
        elif "non_verifie" in statuses or not statuses:
            # explicitly unverified or absent from flags
            unverified.append(t)
        else:
            # statuses like {"ok"}: verified with no exclusion/flag
            pass

    evidence = subset.to_dict(orient="records")
    return {
        "excluded": excluded,
        "flagged": flagged,
        "unverified": unverified,
        "evidence": evidence,
    }
