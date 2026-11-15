"""Fund fees, FX conversion costs and currency risk rules (PRD 5.7, Issue #119).

Every fee, tax rate or withholding rule is a sourced 'assumption' evidence entry with its source URL;
never invent a number.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

# Sourced ETF Management Expense Ratios (MER / RFG).
# Sourced from official fund provider prospectuses and fund overview pages.
ETF_MERS: dict[str, float] = {
    "XIU.TO": 0.0018,    # 0.18% MER
    "SPY": 0.000945,     # 0.0945% Gross Expense Ratio
    "QQQ": 0.0020,       # 0.20% Total Expense Ratio
    "ESGV": 0.0009,      # 0.09% Expense Ratio
    "XBB.TO": 0.0010,    # 0.10% MER
    "ZST.TO": 0.0016,    # 0.16% MER
    "AGG": 0.0003,       # 0.03% Net Expense Ratio
    "TLT": 0.0015,       # 0.15% Expense Ratio
    "GLD": 0.0040,       # 0.40% Gross Expense Ratio
}

ETF_MER_SOURCES: dict[str, dict[str, str]] = {
    "XIU.TO": {
        "name": "iShares S&P/TSX 60 Index ETF",
        "issuer": "BlackRock Canada",
        "url": "https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf",
        "mer_pct": "0,18 %",
    },
    "SPY": {
        "name": "SPDR S&P 500 ETF Trust",
        "issuer": "State Street Global Advisors",
        "url": "https://www.ssga.com/us/en/intermediary/etfs/funds/spdr-sp-500-etf-trust-spy",
        "mer_pct": "0,0945 %",
    },
    "QQQ": {
        "name": "Invesco QQQ Trust (Nasdaq-100)",
        "issuer": "Invesco",
        "url": "https://www.invesco.com/qqq-etf/en/about.html",
        "mer_pct": "0,20 %",
    },
    "ESGV": {
        "name": "Vanguard ESG U.S. Stock ETF",
        "issuer": "Vanguard",
        "url": "https://investor.vanguard.com/investment-products/etfs/profile/esgv",
        "mer_pct": "0,09 %",
    },
    "XBB.TO": {
        "name": "iShares Core Canadian Universe Bond Index ETF",
        "issuer": "BlackRock Canada",
        "url": "https://www.blackrock.com/ca/investors/en/products/239493/ishares-core-canadian-universe-bond-index-etf",
        "mer_pct": "0,10 %",
    },
    "ZST.TO": {
        "name": "BMO Ultra Short-Term Bond ETF",
        "issuer": "BMO Global Asset Management",
        "url": "https://www.bmogam.com/ca-en/advisors/investment-solutions/etfs/bmo-ultra-short-term-bond-etf-zst/",
        "mer_pct": "0,16 %",
    },
    "AGG": {
        "name": "iShares Core U.S. Aggregate Bond ETF",
        "issuer": "BlackRock iShares",
        "url": "https://www.ishares.com/us/products/239458/ishares-core-us-aggregate-bond-etf",
        "mer_pct": "0,03 %",
    },
    "TLT": {
        "name": "iShares 20+ Year Treasury Bond ETF",
        "issuer": "BlackRock iShares",
        "url": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
        "mer_pct": "0,15 %",
    },
    "GLD": {
        "name": "SPDR Gold Shares",
        "issuer": "State Street Global Advisors",
        "url": "https://www.ssga.com/us/en/intermediary/etfs/funds/spdr-gold-shares-gld",
        "mer_pct": "0,40 %",
    },
}

# FX conversion cost assumption: 1.5% retail spread for Canadian brokerages
RETAIL_FX_SPREAD = 0.015
FX_SPREAD_SOURCE = "Grille tarifaire des opérations de change des courtiers canadiens (Questrade / TD / RBC Direct Investing)"
FX_SPREAD_URL = "https://www.questrade.com/pricing/self-directed-commissions-plans-fees/transaction"
NORBERTS_GAMBIT_NOTE = (
    "Pour les montants importants, la manœuvre de Norbert (Norbert's Gambit) via un titre intercoté "
    "(comme DLR/DLR.U) permet de réduire ce coût à environ 0,10 % - 0,20 %."
)

# Currency cap for capital preservation profiles
CAPITAL_PRESERVATION_FOREIGN_BOND_CAP = 0.125
FOREIGN_BOND_SOURCE = "Règle de conception AlphaForge (hypothèse) ; contexte : gestion du risque de change, CFA Institute"
FOREIGN_BOND_URL = "https://www.cfainstitute.org/en/membership/professional-development/refresher-readings/currency-management"
FOREIGN_BOND_REASON = (
    "Pour un profil visant la préservation du capital, chaque FNB obligataire étranger non couvert "
    "en devises (AGG, TLT) est plafonné à 12,5 % afin de limiter le risque de change non rémunéré. "
    "Limite de l'univers : il ne contient que deux FNB obligataires canadiens (XBB.TO, ZST.TO, "
    "25 % chacun au plus) et aucun FNB obligataire couvert en CAD ; environ 25 % du portefeuille "
    "reste donc exposé au dollar américain (obligations américaines ou or). Un plafond à 0 % ne "
    "ferait que déplacer cette part vers l'or, plus volatil."
)


def calculate_fee_drag(weights: dict[str, float] | pd.Series, info: pd.DataFrame | None = None) -> float:
    """Calculate annual fee drag (weighted average MER) for a portfolio."""
    if isinstance(weights, pd.Series):
        w_dict = weights.to_dict()
    else:
        w_dict = weights
    total = 0.0
    for t, w in w_dict.items():
        if not w:
            continue
        mer = 0.0
        if info is not None and "mer" in info.columns and t in info.index:
            val = info.at[t, "mer"]
            if pd.notna(val):
                try:
                    mer = float(val)
                except (ValueError, TypeError):
                    mer = ETF_MERS.get(t, 0.0)
            else:
                mer = ETF_MERS.get(t, 0.0)
        else:
            mer = ETF_MERS.get(t, 0.0)
        total += float(w) * mer
    return round(total, 4)


def etf_mer_evidence(as_of: dt.date) -> list[dict]:
    """Generate assumption evidence entries for all 9 ETFs in the universe."""
    entries = []
    for ticker, data in ETF_MER_SOURCES.items():
        entries.append({
            "value": {
                "metric": "etf_mer",
                "ticker": ticker,
                "name": data["name"],
                "mer": ETF_MERS[ticker],
                "unit": "ratio",
            },
            "source": f"{data['issuer']} (prospectus / fiche FNB)",
            "url": data["url"],
            "date": as_of,
            "method": f"published annual management expense ratio (MER) for {ticker}",
            "confidence": "assumption",
        })
    return entries


def fx_conversion_evidence(as_of: dt.date, usd_share: float, scenario: str) -> dict:
    """Generate assumption evidence entry for FX conversion cost for the USD share of a scenario."""
    return {
        "value": {
            "assumption": "fx_conversion_cost",
            "scenario": scenario,
            "usd_share": round(usd_share, 4),
            "retail_spread": RETAIL_FX_SPREAD,
            "estimated_fx_drag": round(usd_share * RETAIL_FX_SPREAD, 4),
            "norberts_gambit": NORBERTS_GAMBIT_NOTE,
        },
        "source": FX_SPREAD_SOURCE,
        "url": FX_SPREAD_URL,
        "date": as_of,
        "method": "retail CAD/USD foreign exchange conversion spread assumption (1.50 % on USD share)",
        "confidence": "assumption",
    }


def capital_preservation_foreign_bond_evidence(as_of: dt.date) -> dict:
    """Generate assumption evidence entry for foreign bond cap on capital preservation profiles."""
    return {
        "value": {
            "rule": "foreign_fixed_income_cap",
            "cap": CAPITAL_PRESERVATION_FOREIGN_BOND_CAP,
            "objective": "capital_preservation",
            "reason": FOREIGN_BOND_REASON,
        },
        "source": FOREIGN_BOND_SOURCE,
        "url": FOREIGN_BOND_URL,
        "date": as_of,
        "method": "currency risk cap on unhedged foreign fixed income for capital preservation",
        "confidence": "assumption",
    }
