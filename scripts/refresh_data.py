"""Rebuild starter CSVs through YFinanceProvider and report the diff (PRD 5.3, A-8).

One command to refresh AlphaForge AI's dataset for the pitch story:
    uv run python scripts/refresh_data.py [--dry-run] [--target-dir DIR]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from alphaforge import config
from alphaforge.data.yfinance_provider import START, YFinanceProvider


def compute_diff(old_df: pd.DataFrame, new_df: pd.DataFrame, date_col: str = "date") -> dict:
    """Compute summary diff between an existing starter CSV and a newly fetched DataFrame."""
    old_count = len(old_df) if old_df is not None and not old_df.empty else 0
    new_count = len(new_df) if new_df is not None and not new_df.empty else 0

    old_range = f"{old_df[date_col].min()} .. {old_df[date_col].max()}" if old_count > 0 else "n/a"
    new_range = f"{new_df[date_col].min()} .. {new_df[date_col].max()}" if new_count > 0 else "n/a"

    return {
        "old_rows": old_count,
        "new_rows": new_count,
        "diff_rows": new_count - old_count,
        "old_range": old_range,
        "new_range": new_range,
    }


def format_report(
    target_dir: Path,
    prices_diff: dict,
    fx_diff: dict,
    actions_diff: dict,
    new_prices: pd.DataFrame,
    new_fx: pd.DataFrame,
    dry_run: bool = False,
) -> str:
    lines = [
        "=" * 70,
        "AlphaForge AI — Dataset Refresh Report (YFinanceProvider)",
        "=" * 70,
        f"Target directory: {target_dir}",
        f"Mode:             {'DRY RUN (no files modified)' if dry_run else 'APPLIED (files updated)'}",
        "",
        "1. Daily Prices (prices_daily.csv):",
        f"   Rows:          {prices_diff['old_rows']:,} -> {prices_diff['new_rows']:,} ({prices_diff['diff_rows']:+d} rows)",
        f"   Date range:    {prices_diff['old_range']} -> {prices_diff['new_range']}",
    ]

    if new_prices is not None and not new_prices.empty:
        sample_tickers = ["SPY", "XIU.TO", "AAPL", "RY.TO", "BTC-USD"]
        sample_rows = []
        for t in sample_tickers:
            t_rows = new_prices[new_prices["ticker"] == t].sort_values("date")
            if not t_rows.empty:
                last_row = t_rows.iloc[-1]
                sample_rows.append(
                    f"     {t:<10} close={last_row['close']:.2f} {last_row['currency']} "
                    f"({str(last_row['date'])[:10]})"
                )
        if sample_rows:
            lines.append("   Sample latest quotes:")
            lines.extend(sample_rows)

    lines.extend([
        "",
        "2. USD/CAD Exchange Rate (fx_usdcad_daily.csv):",
        f"   Rows:          {fx_diff['old_rows']:,} -> {fx_diff['new_rows']:,} ({fx_diff['diff_rows']:+d} rows)",
        f"   Date range:    {fx_diff['old_range']} -> {fx_diff['new_range']}",
    ])

    if new_fx is not None and not new_fx.empty:
        last_fx = new_fx.sort_values("date").iloc[-1]
        lines.append(f"   Latest rate:   1 USD = {last_fx['usdcad']:.4f} CAD ({str(last_fx['date'])[:10]})")

    lines.extend([
        "",
        "3. Corporate Actions (corporate_actions.csv):",
        f"   Rows:          {actions_diff['old_rows']:,} -> {actions_diff['new_rows']:,} ({actions_diff['diff_rows']:+d} events)",
        f"   Date range:    {actions_diff['old_range']} -> {actions_diff['new_range']}",
        "=" * 70,
    ])
    return "\n".join(lines)


def refresh(
    target_dir: Path | str | None = None,
    out_dir: Path | str | None = None,
    start: str = START,
    end: str | None = None,
    dry_run: bool = False,
) -> tuple[str, dict]:
    """Execute refresh via YFinanceProvider and return (report_text, diff_dict)."""
    target = Path(target_dir or config.STARTER_DIR).resolve()
    dest = Path(out_dir).resolve() if out_dir else target

    # 1. Read existing CSVs
    old_prices = pd.read_csv(target / "prices_daily.csv") if (target / "prices_daily.csv").exists() else pd.DataFrame()
    old_fx = pd.read_csv(target / "fx_usdcad_daily.csv") if (target / "fx_usdcad_daily.csv").exists() else pd.DataFrame()
    old_actions = pd.read_csv(target / "corporate_actions.csv") if (target / "corporate_actions.csv").exists() else pd.DataFrame()

    # 2. Fetch new data via YFinanceProvider
    provider = YFinanceProvider(root=target, start=start, end=end)
    new_prices = provider.prices()
    new_fx = provider.fx()
    new_actions = provider.corporate_actions()

    # 3. Compute diffs
    prices_diff = compute_diff(old_prices, new_prices, date_col="date")
    fx_diff = compute_diff(old_fx, new_fx, date_col="date")
    actions_diff = compute_diff(old_actions, new_actions, date_col="ex_date")

    diff_summary = {
        "prices": prices_diff,
        "fx": fx_diff,
        "corporate_actions": actions_diff,
    }

    report = format_report(
        target_dir=dest,
        prices_diff=prices_diff,
        fx_diff=fx_diff,
        actions_diff=actions_diff,
        new_prices=new_prices,
        new_fx=new_fx,
        dry_run=dry_run,
    )

    # 4. Save if not dry-run
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        new_prices.sort_values(["ticker", "date"]).to_csv(dest / "prices_daily.csv", index=False)
        new_fx.sort_values("date").to_csv(dest / "fx_usdcad_daily.csv", index=False)
        new_actions.sort_values(["ticker", "ex_date"]).to_csv(dest / "corporate_actions.csv", index=False)

    return report, diff_summary


def main():
    parser = argparse.ArgumentParser(description="Refresh AlphaForge AI starter dataset using YFinanceProvider.")
    parser.add_argument("--target-dir", type=Path, default=config.STARTER_DIR, help="Path to starter dataset directory.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional output directory (defaults to target-dir).")
    parser.add_argument("--start", type=str, default=START, help=f"Start date (default: {START}).")
    parser.add_argument("--end", type=str, default=None, help="End date (inclusive, default: today).")
    parser.add_argument("--dry-run", action="store_true", help="Report diff without writing updated CSVs.")

    args = parser.parse_args()
    report, _ = refresh(
        target_dir=args.target_dir,
        out_dir=args.output_dir,
        start=args.start,
        end=args.end,
        dry_run=args.dry_run,
    )
    print(report)


if __name__ == "__main__":
    main()
