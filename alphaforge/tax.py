"""Canadian account types and tax rules (PRD / Issue #118). Track A.

All fee, tax rate or withholding rules are sourced assumptions with source URLs.
Never invent a number.
"""

from __future__ import annotations

import datetime as dt
import functools
from typing import Literal

import pandas as pd

from alphaforge.data.provider import get_provider

AccountType = Literal["tfsa", "rrsp", "fhsa", "non_registered", "mixed"]
VALID_ACCOUNT_TYPES: set[str] = {"tfsa", "rrsp", "fhsa", "non_registered", "mixed"}

# --- Sourced Tax Rates & Statutory Parameters ---------------------------------------------
# 1. Canada-U.S. Tax Treaty (Convention Between Canada and the United States of America
#    with Respect to Taxes on Income and on Capital, Article X and Article XXI):
#    - Article X(2): 15% withholding tax on dividends paid to Canadian residents.
#    - Article XXI(2): Exemption from cross-border withholding tax for pensions/retirement
#      plans (RRSP / RRIF). TFSAs and FHSAs are not recognized as retirement trusts under
#      the treaty, so the 15% withholding is non-recoverable (no Foreign Tax Credit).
US_WITHHOLDING_RATE: float = 0.15
US_TREATY_SOURCE: str = "Convention fiscale Canada - États-Unis (Articles X et XXI)"
US_TREATY_URL: str = (
    "https://www.canada.ca/en/department-finance/programs/tax-policy/tax-treaties/country/"
    "united-states-convention-consolidated-1980-1983-1984-1995-1997-2007.html"
)

# 2. CRA Federal Individual Income Tax Brackets (2024-2025):
#    Federal statutory rate for middle income bracket ($55,867 to $111,733): 20.5%.
#    Line 12100: Interest and other investment income is 100% taxable at ordinary rates.
FEDERAL_MIDDLE_RATE: float = 0.205
CRA_RATES_SOURCE: str = "Agence du revenu du Canada (Paliers d'imposition 2024-2025 et ligne 12100)"
CRA_RATES_URL: str = (
    "https://www.canada.ca/en/revenue-agency/services/tax/individuals/"
    "frequently-asked-questions-individuals/canadian-income-tax-rates-individuals-current-previous-years.html"
)

# 3. CRA Canadian Eligible Dividends (Line 12000, Income Tax Act s. 82(1) and s. 121):
#    - Gross-up factor: 38% (1.38x).
#    - Federal dividend tax credit (DTC): 15.0198% (6/11 of the 38% gross-up).
#    - Net federal effective tax rate = (1.38 * 20.5%) - (1.38 * 15.0198%) = 28.29% - 20.727% = 7.56%.
ELIGIBLE_DIVIDEND_GROSS_UP: float = 0.38
FEDERAL_DTC_RATE: float = 0.150198
CANADIAN_ELIGIBLE_DIVIDEND_NET_RATE: float = round(
    (1 + ELIGIBLE_DIVIDEND_GROSS_UP) * FEDERAL_MIDDLE_RATE
    - (1 + ELIGIBLE_DIVIDEND_GROSS_UP) * FEDERAL_DTC_RATE,
    4,
)  # 0.0756
CRA_DIVIDEND_SOURCE: str = "Agence du revenu du Canada (Ligne 12000 et art. 82(1), 121 LIR)"
CRA_DIVIDEND_URL: str = (
    "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/"
    "about-your-tax-return/tax-return/completing-a-tax-return/personal-income/"
    "line-12000-taxable-amount-dividends-eligible-other-than-eligible-taxable-canadian-corporations.html"
)

# 4. CRA Registered Accounts Reference URLs:
TFSA_URL: str = (
    "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/"
    "tax-free-savings-account.html"
)
RRSP_URL: str = (
    "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/"
    "rrsps-related-plans/registered-retirement-savings-plan-rrsp.html"
)
FHSA_URL: str = (
    "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/"
    "first-home-savings-account.html"
)


# --- Dividend & Income Yield Calculation ---------------------------------------------------


@functools.lru_cache(maxsize=32)
def trailing_yields(as_of: dt.date | pd.Timestamp) -> dict[str, float]:
    """Trailing 12-month dividend / distribution yield per ticker from corporate_actions.csv.

    Yield = sum(dividends in trailing 12 months) / price at as_of.
    Tickers without dividend records in the period receive 0.0.
    """
    provider = get_provider()
    ca = provider.corporate_actions()
    as_of_ts = pd.Timestamp(as_of)
    start_1y = as_of_ts - pd.DateOffset(years=1)

    divs = ca[
        (ca["action"] == "dividend")
        & (ca["ex_date"] <= as_of_ts)
        & (ca["ex_date"] > start_1y)
    ]
    div_sums = divs.groupby("ticker")["value"].sum().to_dict()

    px = provider.prices(end=as_of_ts)
    if px.empty:
        return {}
    last_px = px.sort_values("date").groupby("ticker")["close"].last().to_dict()

    info = provider.asset_info()
    yields: dict[str, float] = {}
    for ticker in info.index:
        d = div_sums.get(ticker, 0.0)
        p = last_px.get(ticker, 0.0)
        yields[ticker] = float(d / p) if p > 0 and d > 0 else 0.0
    return yields


# --- Asset Tax Rate per Account Type -------------------------------------------------------


def asset_tax_rate(ticker: str, account_type: str, info: pd.DataFrame) -> float:
    """The effective tax rate on dividend/interest yield for an asset in a given account type.

    - rrsp: 0.0 (all income tax-sheltered; US dividends exempt under Treaty Art. XXI).
    - tfsa / fhsa: 0.0 on Canadian assets; 15% non-recoverable US withholding on US assets.
    - non_registered:
        * Canadian equity: 7.56% (eligible dividend credit net federal rate).
        * Canadian bonds / fixed income: 20.5% (fully taxable interest).
        * US equity & bonds: 20.5% (ordinary rate; foreign tax credit offsets US 15%).
        * Crypto / gold: 0.0 (no yield).
    - mixed: optimal asset location (bonds and US equity in RRSP at 0.0, Canadian equity in taxable at 7.56%).
    """
    act = account_type.lower() if account_type else "non_registered"
    if act not in VALID_ACCOUNT_TYPES:
        act = "non_registered"

    if act == "rrsp":
        return 0.0

    cls = info.at[ticker, "asset_class"] if ticker in info.index else "equity"
    ccy = info.at[ticker, "currency"] if ticker in info.index else "CAD"

    if cls in ("crypto", "etf_commodity"):
        return 0.0

    is_us = ccy == "USD"
    is_bond = cls == "etf_bond"

    if act in ("tfsa", "fhsa"):
        # US withholding tax is non-recoverable in TFSA / FHSA
        return US_WITHHOLDING_RATE if is_us else 0.0

    if act == "mixed":
        # Asset location: bonds and US equity housed in RRSP (0%), Canadian equity in taxable (7.56%)
        if is_bond or is_us:
            return 0.0
        return CANADIAN_ELIGIBLE_DIVIDEND_NET_RATE

    # non_registered:
    if is_bond or is_us:
        return FEDERAL_MIDDLE_RATE  # 20.5%
    return CANADIAN_ELIGIBLE_DIVIDEND_NET_RATE  # 7.56%


# --- Scenario Tax Drag ---------------------------------------------------------------------


def scenario_tax_drag(
    weights: dict[str, float] | pd.Series,
    account_type: str,
    as_of: dt.date | pd.Timestamp,
    info: pd.DataFrame,
) -> float:
    """Estimated annual tax drag = sum(weight * historical_yield * tax_rate)."""
    yields = trailing_yields(as_of)
    w_dict = weights.to_dict() if isinstance(weights, pd.Series) else weights
    total_drag = 0.0
    for ticker, weight in w_dict.items():
        if weight <= 0 or ticker not in info.index:
            continue
        y = yields.get(ticker, 0.0)
        rate = asset_tax_rate(ticker, account_type, info)
        total_drag += weight * y * rate
    return float(round(total_drag, 4))


# --- Sourced Assumption Evidence Entries --------------------------------------------------


def tax_rules_evidence(as_of: dt.date | pd.Timestamp, account_type: str) -> list[dict]:
    """Sourced assumption evidence items describing Canadian tax and withholding rules."""
    return [
        {
            "value": {
                "rule": "us_dividend_withholding",
                "rate": US_WITHHOLDING_RATE,
                "account_type": account_type,
                "recoverable_in_rrsp": True,
                "recoverable_in_tfsa": False,
                "note": "15 % de retenue à la source américaine sur dividendes d'actions et FNB US ; exonérée en REER (art. XXI), non récupérable en CELI/CELIAPP.",
            },
            "source": US_TREATY_SOURCE,
            "url": US_TREATY_URL,
            "date": as_of if isinstance(as_of, dt.date) else as_of.date(),
            "method": "Convention fiscale Canada - É.-U. art. X(2) (retenue de 15 %) et art. XXI(2) (exonération régimes de retraite / REER)",
            "confidence": "assumption",
        },
        {
            "value": {
                "rule": "canadian_eligible_dividend_tax_credit",
                "gross_up_rate": ELIGIBLE_DIVIDEND_GROSS_UP,
                "federal_dtc_rate": FEDERAL_DTC_RATE,
                "federal_marginal_rate": FEDERAL_MIDDLE_RATE,
                "net_effective_rate": CANADIAN_ELIGIBLE_DIVIDEND_NET_RATE,
                "note": "Dividendes canadiens déterminés dans un compte imposable : majoration de 38 % et crédit d'impôt fédéral de 15,02 %, soit un taux net fédéral de 7,56 % au palier médian (20,5 %).",
            },
            "source": CRA_DIVIDEND_SOURCE,
            "url": CRA_DIVIDEND_URL,
            "date": as_of if isinstance(as_of, dt.date) else as_of.date(),
            "method": "Calcul légal LIR art. 82(1) et 121 : majoration de 38 % et crédit fédéral de 6/11 de la majoration",
            "confidence": "assumption",
        },
        {
            "value": {
                "rule": "canadian_interest_taxation",
                "federal_marginal_rate": FEDERAL_MIDDLE_RATE,
                "note": "Revenus d'intérêt (obligations canadiennes et étrangères) imposables à 100 % au taux marginal ordinaire (palier fédéral médian de 20,5 %).",
            },
            "source": CRA_RATES_SOURCE,
            "url": CRA_RATES_URL,
            "date": as_of if isinstance(as_of, dt.date) else as_of.date(),
            "method": "Ligne 12100 ARC : imposition intégrale des intérêts sans abattement ni crédit d'impôt au taux statutaire",
            "confidence": "assumption",
        },
    ]


# --- Asset Location Notes -----------------------------------------------------------------


def asset_location_note(account_type: str) -> str | None:
    """Asset location note for mixed accounts (PRD / Issue #118)."""
    act = account_type.lower() if account_type else "non_registered"
    if act == "mixed":
        return (
            "Localisation optimale des actifs (asset location) : obligations et actions américaines "
            "logées dans le compte enregistré (REER) pour éliminer l'imposition à taux plein de l'intérêt "
            "et la retenue fiscale américaine ; actions canadiennes logées dans le compte non enregistré "
            "pour bénéficier du crédit d'impôt pour dividendes déterminés."
        )
    return None
