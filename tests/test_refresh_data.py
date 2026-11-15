"""Tests for dataset refresh script (scripts/refresh_data.py)."""

from unittest.mock import MagicMock, patch

import pandas as pd

from scripts.refresh_data import compute_diff, format_report, refresh


def test_compute_diff_calculates_row_counts_and_ranges():
    old_df = pd.DataFrame({
        "date": ["2021-11-12", "2021-11-13"],
        "val": [1.0, 2.0],
    })
    new_df = pd.DataFrame({
        "date": ["2021-11-12", "2021-11-13", "2021-11-14"],
        "val": [1.0, 2.0, 3.0],
    })

    diff = compute_diff(old_df, new_df, date_col="date")
    assert diff["old_rows"] == 2
    assert diff["new_rows"] == 3
    assert diff["diff_rows"] == 1
    assert diff["old_range"] == "2021-11-12 .. 2021-11-13"
    assert diff["new_range"] == "2021-11-12 .. 2021-11-14"


def test_compute_diff_handles_empty_frames():
    diff = compute_diff(pd.DataFrame(), pd.DataFrame())
    assert diff["old_rows"] == 0
    assert diff["new_rows"] == 0
    assert diff["diff_rows"] == 0
    assert diff["old_range"] == "n/a"
    assert diff["new_range"] == "n/a"


def test_format_report_includes_key_sections():
    prices_diff = {
        "old_rows": 100, "new_rows": 120, "diff_rows": 20,
        "old_range": "2021-11-12 .. 2026-11-12", "new_range": "2021-11-12 .. 2026-11-15",
    }
    fx_diff = {
        "old_rows": 50, "new_rows": 55, "diff_rows": 5,
        "old_range": "2021-11-12 .. 2026-11-12", "new_range": "2021-11-12 .. 2026-11-15",
    }
    actions_diff = {
        "old_rows": 10, "new_rows": 12, "diff_rows": 2,
        "old_range": "2021-11-12 .. 2026-11-12", "new_range": "2021-11-12 .. 2026-11-15",
    }
    sample_prices = pd.DataFrame({
        "date": ["2026-11-15"], "ticker": ["SPY"],
        "close": [750.0], "currency": ["USD"],
    })
    sample_fx = pd.DataFrame({
        "date": ["2026-11-15"], "usdcad": [1.42], "cadusd": [0.7042],
    })

    report = format_report(
        target_dir="/tmp/test",
        prices_diff=prices_diff,
        fx_diff=fx_diff,
        actions_diff=actions_diff,
        new_prices=sample_prices,
        new_fx=sample_fx,
        dry_run=True,
    )

    assert "DRY RUN" in report
    assert "Daily Prices" in report
    assert "+20 rows" in report
    assert "USD/CAD Exchange Rate" in report
    assert "+5 rows" in report
    assert "Corporate Actions" in report
    assert "+2 events" in report
    assert "SPY" in report


def test_refresh_dry_run_and_write(tmp_path):
    # Setup dummy existing CSVs
    target_dir = tmp_path / "starter"
    target_dir.mkdir()
    old_px = pd.DataFrame({"date": ["2021-11-12"], "ticker": ["SPY"], "close": [400.0]})
    old_px.to_csv(target_dir / "prices_daily.csv", index=False)

    mock_provider = MagicMock()
    mock_provider.prices.return_value = pd.DataFrame({
        "date": ["2021-11-12", "2021-11-13"], "ticker": ["SPY", "SPY"],
        "open": [400.0, 405.0], "high": [405.0, 410.0], "low": [399.0, 404.0],
        "close": [404.0, 409.0], "adj_close": [404.0, 409.0], "volume": [1000, 1200],
        "currency": ["USD", "USD"],
    })
    mock_provider.fx.return_value = pd.DataFrame({
        "date": ["2021-11-12", "2021-11-13"], "usdcad": [1.25, 1.26], "cadusd": [0.80, 0.7936],
    })
    mock_provider.corporate_actions.return_value = pd.DataFrame({
        "ex_date": ["2021-11-13"], "ticker": ["SPY"], "action": ["dividend"],
        "value": [1.5], "unit": ["USD per share"],
    })

    with patch("scripts.refresh_data.YFinanceProvider", return_value=mock_provider):
        # 1. Dry run
        report, diff = refresh(target_dir=target_dir, dry_run=True)
        assert diff["prices"]["diff_rows"] == 1
        assert "DRY RUN" in report
        # File should not be overwritten in dry run
        read_back = pd.read_csv(target_dir / "prices_daily.csv")
        assert len(read_back) == 1

        # 2. Real write
        report_write, diff_write = refresh(target_dir=target_dir, dry_run=False)
        assert diff_write["prices"]["diff_rows"] == 1
        assert "APPLIED" in report_write
        read_back_after = pd.read_csv(target_dir / "prices_daily.csv")
        assert len(read_back_after) == 2
        assert (target_dir / "fx_usdcad_daily.csv").exists()
        assert (target_dir / "corporate_actions.csv").exists()
