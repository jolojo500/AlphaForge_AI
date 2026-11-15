"""Macro (PRD 5.4). Track A: rates and inflation as they were actually known on the as-of date.

Monthly series in macro_rates.csv are dated to their reference month, not their release:
February CPI is only public in March. Each series gets an assumed publication date, and a
value is used only if it was published on or before the as-of date.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from alphaforge.data.provider import get_provider
from alphaforge.evidence import EvidenceRegistry
from alphaforge.state import GraphState
from alphaforge.tracing import traced

# series_id -> (metric, rule, n)
#   "bday":         published n business days after the observation date
#   "month":        published on day n of the month after the reference month
#   "first_friday": published on the first Friday of the month after the reference month
# Release days are set slightly late on purpose, so we never use a number before it existed:
#   Statistics Canada CPI ~3rd week, BLS CPI ~mid-month, BLS jobs report / StatCan LFS first Friday.
SERIES = {
    "V39079": ("policy_rate_ca", "bday", 1),
    "BD.CDN.2YR.DQ.YLD": ("yield_2y_ca", "bday", 1),
    "BD.CDN.10YR.DQ.YLD": ("yield_10y_ca", "bday", 1),
    "STATIC_TOTALCPICHANGE": ("cpi_yoy_ca", "month", 20),
    "v2062815": ("unemployment_ca", "first_friday", 1),
    "14-10-0287-01": ("unemployment_ca", "first_friday", 1),
    "DFF": ("policy_rate_us", "bday", 1),
    "DGS2": ("yield_2y_us", "bday", 1),
    "DGS10": ("yield_10y_us", "bday", 1),
    "CPIAUCSL": ("cpi_index_us", "month", 15),
    "UNRATE": ("unemployment_us", "month", 7),
}
RATE_SERIES = ("V39079", "BD.CDN.2YR.DQ.YLD", "BD.CDN.10YR.DQ.YLD", "DFF", "DGS2", "DGS10")
METRIC_ORDER = (
    "policy_rate_ca", "yield_2y_ca", "yield_10y_ca", "curve_slope_ca", "cpi_yoy_ca", "unemployment_ca",
    "policy_rate_us", "yield_2y_us", "yield_10y_us", "curve_slope_us", "cpi_yoy_us",
    "unemployment_us",
)


def _rule_text(series_id: str) -> str:
    _, rule, n = SERIES[series_id]
    if rule == "bday":
        return f"{n} business day after the observation"
    if rule == "first_friday":
        return "first Friday of the month after the reference month"
    return f"day {n} of the month after the reference month"


def published_on(series_id: str, ref_dates: pd.Series) -> pd.Series:
    """Assumed publication date for each observation date of a series."""
    _, rule, n = SERIES[series_id]
    if rule == "bday":
        days = np.busday_offset(ref_dates.to_numpy().astype("datetime64[D]"), n, roll="backward")
        return pd.Series(pd.to_datetime(days), index=ref_dates.index)
    if rule == "first_friday":
        first_day = (ref_dates.dt.to_period("M") + 1).dt.to_timestamp()
        offset = (4 - first_day.dt.day_of_week) % 7
        return first_day + pd.to_timedelta(offset, unit="D")
    return (ref_dates.dt.to_period("M") + 1).dt.to_timestamp() + pd.Timedelta(days=n - 1)


def latest(macro: pd.DataFrame, series_id: str, as_of: dt.date) -> dict | None:
    """Most recent observation of a series that was published on or before `as_of`."""
    rows = macro[macro["series_id"] == series_id].sort_values("date")
    if rows.empty:
        return None
    published = published_on(series_id, rows["date"])
    known = rows[published <= pd.Timestamp(as_of)]
    if known.empty:
        return None
    row = known.iloc[-1]
    return {
        "value": float(row["value"]),
        "ref_date": row["date"].date(),
        "published": published.loc[row.name].date(),
        "label": row["label"],
        "source": row["source"],
        "series_id": series_id,
        "rule": _rule_text(series_id),
    }


def rates_as_of(as_of: dt.date, macro: pd.DataFrame | None = None) -> dict[str, dict]:
    """Policy rates and 2y/10y yields for Canada and the US, plus the 10y-2y slope."""
    macro = get_provider().macro() if macro is None else macro
    out = {}
    for sid in RATE_SERIES:
        hit = latest(macro, sid, as_of)
        if hit:
            out[SERIES[sid][0]] = hit
    for c in ("ca", "us"):
        y2, y10 = out.get(f"yield_2y_{c}"), out.get(f"yield_10y_{c}")
        if y2 and y10:
            out[f"curve_slope_{c}"] = {
                "value": round(y10["value"] - y2["value"], 4),
                "ref_date": min(y2["ref_date"], y10["ref_date"]),
                "published": max(y2["published"], y10["published"]),
                "label": f"10-year minus 2-year government yield ({c.upper()})",
                "source": y10["source"],
                "series_id": f"{y10['series_id']} - {y2['series_id']}",
                "rule": y10["rule"],
            }
    return out


def inflation_as_of(as_of: dt.date, macro: pd.DataFrame | None = None) -> dict[str, dict]:
    """CPI y/y for Canada (published as a % change) and the US (computed from the index),
    plus US and Canadian unemployment."""
    macro = get_provider().macro() if macro is None else macro
    out = {}
    ca = latest(macro, "STATIC_TOTALCPICHANGE", as_of)
    if ca:
        out["cpi_yoy_ca"] = ca
    us = latest(macro, "CPIAUCSL", as_of)
    if us:
        year_before = pd.Timestamp(us["ref_date"]) - pd.DateOffset(years=1)
        rows = macro[(macro["series_id"] == "CPIAUCSL") & (macro["date"] == year_before)]
        if not rows.empty:
            yoy = (us["value"] / float(rows["value"].iloc[0]) - 1) * 100
            out["cpi_yoy_us"] = us | {
                "value": round(yoy, 4),
                "label": "U.S. CPI, % change y/y (computed from the SA index)",
            }
    ca_unemployment = latest(macro, "v2062815", as_of) or latest(macro, "14-10-0287-01", as_of)
    if ca_unemployment:
        out["unemployment_ca"] = ca_unemployment
    unemployment = latest(macro, "UNRATE", as_of)
    if unemployment:
        out["unemployment_us"] = unemployment
    return out


@traced("macro")
def macro_node(state: GraphState) -> dict:
    reg = EvidenceRegistry("EM")
    as_of = state.as_of_date
    macro = get_provider().macro()
    facts = rates_as_of(as_of, macro) | inflation_as_of(as_of, macro)

    for metric in METRIC_ORDER:
        f = facts.get(metric)
        if f is None:
            reg.add(
                f"Indicateur {metric} non disponible au {as_of} (aucune publication connue à cette date).",
                source="macro_rates.csv",
                date=as_of,
                method="as-of filter with assumed publication lags",
                confidence="assumption",
            )
            continue
        reg.add(
            {"metric": metric, "value": f["value"], "unit": "%"},
            source=f"macro_rates.csv ({f['source']})",
            date=f["ref_date"],
            date_kind="observation",
            method=(
                f"{f['label']} [{f['series_id']}]; observation {f['ref_date']}, assumed "
                f"published {f['published']} ({f['rule']}); latest value known on {as_of}"
            ),
        )
    if "unemployment_ca" not in facts:
        reg.add(
            "Le taux de chômage canadien ne fait pas partie des données fournies.",
            source="macro_rates.csv",
            date=as_of,
            method="coverage of the starter dataset",
            confidence="assumption",
        )
    return {
        "evidence": reg.items(),
        "summary": f"Contexte macro connu au {as_of} : {len(facts)} indicateurs, délais de publication appliqués.",
    }
