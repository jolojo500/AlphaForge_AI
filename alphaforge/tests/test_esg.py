from __future__ import annotations

from pathlib import Path

import pandas as pd

from alphaforge.app.tools.esg import esg_screen, load_esg_flags


def test_load_esg_flags_has_required_columns():
    df = load_esg_flags()
    required = {
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
    }
    assert required.issubset(df.columns)
    assert len(df) >= 31
    assert set(df["status"]).issubset({"exclude", "flag", "ok", "non_verifie"})


def test_esg_screen_classifies_known_tickers():
    result = esg_screen(["CNQ.TO", "ENB.TO", "XOM", "ESGV", "AAPL", "BTC-USD"])
    assert "CNQ.TO" in result["excluded"]
    assert "ENB.TO" in result["excluded"]
    assert "XOM" in result["excluded"]
    assert "ESGV" not in result["excluded"]
    assert "ESGV" not in result["flagged"]
    assert "ESGV" not in result["unverified"]
    # unverified examples present
    assert "AAPL" in result["unverified"]
    assert "BTC-USD" in result["unverified"]
    assert isinstance(result["evidence"], list)
    assert any(r["ticker"] == "CNQ.TO" for r in result["evidence"])


def test_esg_screen_unknown_ticker_is_unverified():
    result = esg_screen(["ZZZZ"])
    assert result["excluded"] == []
    assert result["flagged"] == []
    assert result["unverified"] == ["ZZZZ"]
    assert result["evidence"] == []


def test_esg_screen_accepts_preloaded_dataframe(tmp_path: Path):
    df = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "criterion": "test",
                "status": "flag",
                "evidence_text": "e",
                "source_name": "s",
                "source_url": "u",
                "document_page": "",
                "published_date": "",
                "retrieved_date": "2026-11-14",
                "license_note": "n",
            },
            {
                "ticker": "BBB",
                "criterion": "test",
                "status": "exclude",
                "evidence_text": "e",
                "source_name": "s",
                "source_url": "u",
                "document_page": "",
                "published_date": "",
                "retrieved_date": "2026-11-14",
                "license_note": "n",
            },
        ]
    )
    result = esg_screen(["aaa", "BBB", "CCC"], flags_df=df)
    assert result["flagged"] == ["AAA"]
    assert result["excluded"] == ["BBB"]
    assert result["unverified"] == ["CCC"]
