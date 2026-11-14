"""Tests for alphaforge.app.tools.news (dated news / EDGAR filings)."""

from __future__ import annotations

import pandas as pd
import pytest

from alphaforge.app.tools.news import news_for, load_news_references


def test_news_loads():
    df = load_news_references()
    assert not df.empty
    assert {"published_date", "ticker", "title", "form_or_type", "url", "source", "retrieved_date"}.issubset(df.columns)
    assert set(df["ticker"].unique()) == {"TSLA", "NVDA"}


def test_news_no_lookahead():
    cutoff = "2024-01-01"
    items = news_for("TSLA", cutoff)
    assert len(items) >= 0
    for item in items:
        assert item["published_date"] <= cutoff


def test_news_filters_ticker():
    items = news_for("TSLA", "2026-12-31")
    assert all(item["ticker"] == "TSLA" for item in items)
    nvda = news_for("NVDA", "2026-12-31")
    assert all(item["ticker"] == "NVDA" for item in nvda)


def test_news_empty_before_early_date():
    items = news_for("TSLA", "2000-01-01")
    assert len(items) == 0


def test_news_accepts_datetime():
    items = news_for("NVDA", pd.Timestamp("2025-01-01"))
    for item in items:
        assert item["published_date"] <= "2025-01-01"


def test_news_dataframe_access():
    df = news_for("TSLA", "2026-12-31")
    assert "published_date" in df.columns
    assert len(df) > 0
