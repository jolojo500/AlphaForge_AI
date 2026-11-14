"""Investor personas and structured constraint specifications for AlphaForge AI.

Covers the three official reference personas from the PolyFinances 2026 Datathon:
- Amira (26, High risk, 15+ years): AI & emerging tech, crypto, diversification.
- Mateo (41, Moderate risk, 8-12 years): ESG preferences, balance growth and stability, exclude speculative.
- Robert (59, Low-to-moderate risk, 3-5 years): Capital preservation, retirement proximity, high-profile temptation (TSLA).

Implements Phase 1b Two-Level Strategic Sleeve Architecture:
- Level 1: Strategic sleeve weights (Equity, Bonds, Crypto, Gold/Cash) aligned with horizon and risk capacity.
- Level 2: Quantitative intra-sleeve optimization with preference tilts (tech/AI floor, ESG screening, bond duration).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from alphaforge.app.tools.optimize import StrategicSleeveConfig


@dataclass
class ESGExclusionNote:
    ticker: str
    reason: str
    source: str = "hypothese_equipe — à remplacer par source ESG"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class PersonaConstraints:
    target_vol_band: tuple[float, float]
    single_asset_cap: float
    bond_floor: float
    crypto_cap: float
    sector_caps: dict[str, float] = field(default_factory=dict)
    sector_floors: dict[str, float] = field(default_factory=dict)
    class_caps: dict[str, float] = field(default_factory=dict)
    class_floors: dict[str, float] = field(default_factory=dict)
    per_asset_caps: dict[str, float] = field(default_factory=dict)
    per_asset_floors: dict[str, float] = field(default_factory=dict)
    exclusions: list[str] = field(default_factory=list)
    preferred_tickers: list[str] = field(default_factory=list)
    strategic_sleeves: list[StrategicSleeveConfig] = field(default_factory=list)
    provisional_esg_exclusions: list[ESGExclusionNote] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        return res


@dataclass
class Persona:
    id: str
    name: str
    age: int
    profession: str
    family_status: str
    investment_experience: str
    investment_objective: str
    horizon_label: str
    horizon_years_min: int
    horizon_years_max: int
    risk_profile: Literal["high", "moderate", "low_to_moderate"]
    case_preferences: list[str]
    reality_test: str
    team_assumptions: dict[str, str]
    constraints: PersonaConstraints

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_amira_persona() -> Persona:
    """Amira: 26yo, High risk, 15+ years horizon.

    Strategic Sleeves: Equity 80% / Crypto 10% / Bonds 5% / Gold 5%.
    Intra-sleeve: Tech floor 45% of equity (36% total), NVDA floor >= 4.8% total, crypto 10%.
    """
    team_assumptions = {
        "strategic_sleeves": "Equity 80% / Crypto 10% / Bonds 5% / Gold 5% based on 15+ yr aggressive horizon.",
        "tech_ai_floor": "Tech sector floor set at 45% of equity (36% total portfolio), with NVDA floor >= 4.8% to guarantee observable AI exposure as tested by case.",
        "single_asset_cap": "Individual equities capped at 12.5% of equity sleeve (<= 10% total portfolio) to enforce diversification.",
        "crypto_allocation": "10% strategic allocation split equally between Bitcoin and Ether (5% BTC, 5% ETH) to capture growth without exceeding 15% ceiling.",
        "target_volatility_band": "Target volatility band 12.0% to 20.0% annualized.",
    }

    sleeves = [
        StrategicSleeveConfig(
            name="equity",
            target_weight=0.80,
            weight_band=(0.75, 0.85),
            asset_classes=["equity", "etf_equity"],
            single_asset_cap=0.125,  # 10% of total portfolio
            per_asset_caps=0.125,  # 10% of total portfolio
            per_asset_floors={"NVDA": 0.06, "MSFT": 0.06, "AAPL": 0.06},  # 4.8% each total
            sector_floors={"Information Technology": 0.45},  # 36% total
            sector_caps={"Information Technology": 0.50},  # 40% total
            exclusions=[],
            rationale="Aggressive equity core with direct exposure to AI leaders (NVDA, MSFT, AAPL, CSU.TO, SHOP.TO) while maintaining non-tech diversification.",
        ),
        StrategicSleeveConfig(
            name="crypto",
            target_weight=0.10,
            weight_band=(0.05, 0.10),
            asset_classes=["crypto"],
            fixed_allocations={"BTC-USD": 0.50, "ETH-USD": 0.50},
            rationale="Captures cryptoasset upside aligned with high risk tolerance and 15+ yr horizon, capped at 10% to prevent catastrophic drawdown.",
        ),
        StrategicSleeveConfig(
            name="bonds",
            target_weight=0.05,
            weight_band=(0.05, 0.10),
            asset_classes=["etf_bond"],
            fixed_allocations={"ZST.TO": 1.0},
            rationale="Minimal ultra short-term bond cushion for liquidity.",
        ),
        StrategicSleeveConfig(
            name="gold_cash",
            target_weight=0.05,
            weight_band=(0.0, 0.05),
            asset_classes=["etf_commodity"],
            fixed_allocations={"GLD": 1.0},
            rationale="Non-correlated commodity buffer.",
        ),
    ]

    constraints = PersonaConstraints(
        target_vol_band=(0.12, 0.20),
        single_asset_cap=0.10,
        bond_floor=0.05,
        crypto_cap=0.10,
        sector_caps={"Information Technology": 0.40},
        sector_floors={"Information Technology": 0.30},
        class_caps={"crypto": 0.10, "etf_bond": 0.10},
        class_floors={"crypto": 0.05, "equity": 0.75},
        per_asset_caps={"NVDA": 0.10, "AAPL": 0.10, "MSFT": 0.10, "BTC-USD": 0.05, "ETH-USD": 0.05},
        per_asset_floors={"NVDA": 0.04},
        exclusions=[],
        preferred_tickers=["NVDA", "AAPL", "MSFT", "SHOP.TO", "CSU.TO", "BTC-USD", "ETH-USD"],
        strategic_sleeves=sleeves,
    )

    return Persona(
        id="amira",
        name="Amira",
        age=26,
        profession="Software engineer",
        family_status="Single, no children",
        investment_experience="Intermediate",
        investment_objective="Long-term capital growth",
        horizon_label="15 years or more",
        horizon_years_min=15,
        horizon_years_max=30,
        risk_profile="high",
        case_preferences=[
            "Very interested in artificial intelligence and emerging technologies",
            "Open to high-growth companies and significant volatility",
            "Interested in crypto assets",
            "Still wants some diversification and does not want to invest exclusively in technology",
        ],
        reality_test="How much risk will the system accept? It should account for an aggressive profile without interpreting 'high risk' as 'anything goes,' while respecting Amira's desire for diversification.",
        team_assumptions=team_assumptions,
        constraints=constraints,
    )


def get_mateo_persona() -> Persona:
    """Mateo: 41yo, Moderate risk, 8-12 years horizon.

    Strategic Sleeves: Equity 60% / Bonds 35% / Gold 5% / Crypto 0%.
    Intra-sleeve: Explicit provisional ESG exclusions (CNQ.TO, ENB.TO, XOM), ESGV core holding >= 15% total.
    """
    provisional_esg = [
        ESGExclusionNote(ticker="CNQ.TO", reason="Oil sands exploration and production"),
        ESGExclusionNote(ticker="ENB.TO", reason="Crude oil and liquids pipeline transmission"),
        ESGExclusionNote(ticker="XOM", reason="Integrated fossil fuel oil and gas exploration"),
    ]

    team_assumptions = {
        "strategic_sleeves": "Equity 60% / Bonds 35% / Gold 5% / Crypto 0% for 8-12 yr balanced family growth.",
        "provisional_esg_exclusions": "Oil sands, pipelines, and fossil fuels (CNQ.TO, ENB.TO, XOM) excluded under provisional team hypothesis pending dedicated ESG dataset (ref GitHub issue #4).",
        "esg_core_holding": "Vanguard ESG U.S. Stock ETF (ESGV) allocated as core holding at >= 25% of equity (>= 15% total portfolio).",
        "speculative_crypto_exclusion": "Cryptoassets (BTC-USD, ETH-USD) strictly 0% per case preference to avoid speculative instruments.",
        "target_volatility_band": "Target volatility band 6.0% to 11.0% annualized.",
    }

    sleeves = [
        StrategicSleeveConfig(
            name="equity",
            target_weight=0.60,
            weight_band=(0.55, 0.65),
            asset_classes=["equity", "etf_equity"],
            single_asset_cap=0.166,  # 10% of total portfolio (0.166 * 0.60 = 0.10)
            per_asset_caps={"ESGV": 0.35},  # ESGV core ETF up to 21% of total portfolio
            per_asset_floors={"ESGV": 0.25},  # 15% total portfolio
            sector_caps={"Energy": 0.0},  # Fossil energy excluded
            exclusions=["CNQ.TO", "ENB.TO", "XOM"],
            rationale="Balanced equity core anchored by ESG-screened US equity (ESGV) and non-fossil Canadian/US dividend companies.",
        ),
        StrategicSleeveConfig(
            name="bonds",
            target_weight=0.35,
            weight_band=(0.30, 0.40),
            asset_classes=["etf_bond"],
            per_asset_caps=0.50,  # <= 17.5% per bond ETF in total portfolio
            rationale="Fixed income stability sleeve (ZST.TO, XBB.TO, AGG) providing capital preservation across 8-12 yr horizon.",
        ),
        StrategicSleeveConfig(
            name="gold_cash",
            target_weight=0.05,
            weight_band=(0.0, 0.05),
            asset_classes=["etf_commodity"],
            fixed_allocations={"GLD": 1.0},
            rationale="Commodity hedge against stagflation / inflation.",
        ),
    ]

    constraints = PersonaConstraints(
        target_vol_band=(0.06, 0.11),
        single_asset_cap=0.10,
        bond_floor=0.30,
        crypto_cap=0.0,
        sector_caps={"Energy": 0.0},
        class_caps={"crypto": 0.0, "etf_bond": 0.40},
        class_floors={"etf_bond": 0.30, "equity": 0.55},
        per_asset_caps={"ESGV": 0.25},
        per_asset_floors={"ESGV": 0.15},
        exclusions=["BTC-USD", "ETH-USD", "CNQ.TO", "ENB.TO", "XOM"],
        preferred_tickers=["ESGV", "XIU.TO", "XBB.TO", "ZST.TO", "AGG", "CNR.TO", "FTS.TO"],
        strategic_sleeves=sleeves,
        provisional_esg_exclusions=provisional_esg,
    )

    return Persona(
        id="mateo",
        name="Mateo",
        age=41,
        profession="Operations manager",
        family_status="Partner and two children",
        investment_experience="Intermediate",
        investment_objective="Balanced capital growth over medium and long term",
        horizon_label="8 to 12 years",
        horizon_years_min=8,
        horizon_years_max=12,
        risk_profile="moderate",
        case_preferences=[
            "Places high importance on Environmental, Social, and Governance (ESG) factors",
            "Wants to avoid companies involved in significant environmental or social controversies",
            "Seeks a balance between growth potential and stability",
            "Open to emerging technologies when they fit his risk profile, but has little interest in highly speculative investments",
        ],
        reality_test="Can the system incorporate more than return and risk? It should consider financial factors and personal preferences, rather than selecting solely for potential return.",
        team_assumptions=team_assumptions,
        constraints=constraints,
    )


def get_robert_persona() -> Persona:
    """Robert: 59yo, Low-to-moderate risk, 3-5 years horizon (near retirement).

    Strategic Sleeves: Bonds 65% / Equity 30% / Gold 5% / Crypto 0%.
    Intra-sleeve: High quality dividend equities (RY, TD, JNJ, PG, FTS). TSLA excluded in baseline, capped at 3% in alternative.
    """
    team_assumptions = {
        "strategic_sleeves": "Bonds 65% / Equity 30% / Gold 5% / Crypto 0% for imminent retirement capital preservation.",
        "bond_duration_mix": "Combines ultra short-term bonds (ZST.TO) and aggregate bonds (XBB.TO, AGG) to mitigate interest rate duration risk as observed in 2022.",
        "crypto_prohibition": "Cryptoassets strictly 0% (blocking rule) due to short horizon and capital preservation mandate.",
        "tsla_hyped_asset_policy": "When Robert requests TSLA, system issues Incoherence Warning and proposes a capped satellite alternative of at most 3.0% (10% of equity sleeve), preserving 65% bonds.",
        "target_volatility_band": "Target volatility band 3.5% to 6.0% annualized.",
    }

    sleeves = [
        StrategicSleeveConfig(
            name="bonds",
            target_weight=0.65,
            weight_band=(0.55, 0.75),
            asset_classes=["etf_bond"],
            single_asset_cap=0.55,  # <= 35.75% of total portfolio per bond ETF
            per_asset_caps=0.55,
            rationale="Heavy capital preservation anchor protecting imminent retirement capital.",
        ),
        StrategicSleeveConfig(
            name="equity",
            target_weight=0.30,
            weight_band=(0.25, 0.35),
            asset_classes=["equity", "etf_equity"],
            single_asset_cap=0.25,  # <= 7.5% of total portfolio per stock
            per_asset_caps=0.25,
            exclusions=["TSLA"],  # Excluded in baseline
            rationale="Defensive high-quality dividend equities generating modest growth without severe drawdowns.",
        ),
        StrategicSleeveConfig(
            name="gold_cash",
            target_weight=0.05,
            weight_band=(0.0, 0.05),
            asset_classes=["etf_commodity"],
            fixed_allocations={"GLD": 1.0},
            rationale="Safe-haven store of value.",
        ),
    ]

    constraints = PersonaConstraints(
        target_vol_band=(0.035, 0.060),
        single_asset_cap=0.08,
        bond_floor=0.55,
        crypto_cap=0.0,
        sector_caps={},
        class_caps={"crypto": 0.0},
        class_floors={"etf_bond": 0.55, "equity": 0.25},
        per_asset_caps={"ZST.TO": 0.35, "XBB.TO": 0.35, "AGG": 0.35, "TSLA": 0.03},
        exclusions=["BTC-USD", "ETH-USD", "TSLA"],
        preferred_tickers=["ZST.TO", "XBB.TO", "AGG", "RY.TO", "TD.TO", "JNJ", "PG", "FTS.TO", "XIU.TO"],
        strategic_sleeves=sleeves,
    )

    return Persona(
        id="robert",
        name="Robert",
        age=59,
        profession="Healthcare professional",
        family_status="Married, adult children, approaching retirement",
        investment_experience="Advanced",
        investment_objective="Preserve capital while maintaining some growth potential",
        horizon_label="3 to 5 years",
        horizon_years_min=3,
        horizon_years_max=5,
        risk_profile="low_to_moderate",
        case_preferences=[
            "Prefers established companies and investments whose business models he understands",
            "Values stability and company quality and has little interest in crypto assets",
            "Follows markets actively and is interested in new opportunities",
            "May be tempted by a highly publicized company even when it is riskier than he would normally prefer",
        ],
        reality_test="Can the system challenge a request that conflicts with the investor's profile? It should identify the tension between Robert's immediate interest and his objectives, explain the risks, and avoid simply agreeing.",
        team_assumptions=team_assumptions,
        constraints=constraints,
    )


PERSONAS: dict[str, Persona] = {
    "amira": get_amira_persona(),
    "mateo": get_mateo_persona(),
    "robert": get_robert_persona(),
}


def get_persona(persona_id: str) -> Persona:
    """Retrieve persona by identifier ('amira', 'mateo', 'robert')."""
    pid = persona_id.lower().strip()
    if pid not in PERSONAS:
        raise KeyError(f"Unknown persona '{persona_id}'. Supported: {list(PERSONAS.keys())}")
    return PERSONAS[pid]
