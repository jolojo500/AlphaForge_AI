"""Investor personas and structured constraint specifications for AlphaForge AI.

Covers the three official reference personas from the PolyFinances 2026 Datathon:
- Amira (26, High risk, 15+ years): AI & emerging tech, crypto, diversification.
- Mateo (41, Moderate risk, 8-12 years): ESG preferences, balance growth and stability, exclude speculative.
- Robert (59, Low-to-moderate risk, 3-5 years): Capital preservation, retirement proximity, high-profile temptation (TSLA).

All team assumptions used to operationalize qualitative case text into quantitative constraints
are explicitly documented.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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

    Tests: System must allow aggressive tech/crypto growth without abandoning diversification.
    """
    team_assumptions = {
        "single_asset_cap": "Capped at 10% to prevent excessive idiosyncratic stock concentration (e.g. NVDA or SHOP alone).",
        "tech_sector_cap": "Capped at 40% (case rule: 'does not want to invest exclusively in technology').",
        "crypto_class_cap": "Capped at 15% combined (BTC + ETH) to allow meaningful growth while bounding catastrophic drawdowns (>70%).",
        "diversification_floor": "Non-tech equities and broad funds must make up at least 45% of portfolio.",
        "target_volatility": "Target volatility band 16% to 24% annualized (high risk, aggressive growth).",
    }

    constraints = PersonaConstraints(
        target_vol_band=(0.16, 0.24),
        single_asset_cap=0.10,
        bond_floor=0.0,
        crypto_cap=0.15,
        sector_caps={
            "Information Technology": 0.40,
        },
        sector_floors={
            "Information Technology": 0.25,
        },
        class_caps={
            "crypto": 0.15,
            "etf_bond": 0.05,
        },
        class_floors={
            "crypto": 0.05,
        },
        per_asset_caps={},
        per_asset_floors={},
        exclusions=[],
        preferred_tickers=["AAPL", "MSFT", "NVDA", "SHOP.TO", "CSU.TO", "QQQ", "BTC-USD", "ETH-USD"],
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

    Tests: System must balance growth & stability, and integrate explicit non-financial ESG preferences.
    """
    team_assumptions = {
        "esg_screening": "Prefers ESG-screened US equity ETF (ESGV) over standard SPY. Excludes traditional fossil fuel energy (XOM, CNQ.TO, ENB.TO capped strictly at 0% or <=5%).",
        "speculative_exclusion": "Excludes crypto assets (BTC-USD, ETH-USD) per case text ('little interest in highly speculative investments').",
        "bond_floor": "Bonds set to >= 25% to ensure balance between growth and capital stability.",
        "single_asset_cap": "Capped at 10% per individual asset.",
        "target_volatility": "Target volatility band 8% to 14% annualized (moderate risk).",
    }

    constraints = PersonaConstraints(
        target_vol_band=(0.08, 0.14),
        single_asset_cap=0.10,
        bond_floor=0.30,
        crypto_cap=0.0,
        sector_caps={
            "Energy": 0.05,
        },
        sector_floors={},
        class_caps={
            "crypto": 0.0,
            "etf_bond": 0.50,
        },
        class_floors={
            "etf_bond": 0.30,
        },
        per_asset_caps={
            "ZST.TO": 0.25,
            "XBB.TO": 0.25,
            "AGG": 0.25,
            "TLT": 0.25,
            "ESGV": 0.25,
        },
        per_asset_floors={
            "ESGV": 0.15,
        },
        exclusions=["BTC-USD", "ETH-USD", "XOM"],
        preferred_tickers=["ESGV", "XIU.TO", "XBB.TO", "ZST.TO", "AGG", "CNR.TO", "FTS.TO"],
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

    Tests: System must challenge hyped/speculative requests (e.g. TSLA), explain risk, and avoid blindly complying.
    """
    team_assumptions = {
        "capital_preservation_priority": "Horizon of 3-5 years before retirement requires high capital preservation.",
        "bond_floor": "Fixed income + cash equivalents >= 50% (XBB.TO, ZST.TO, AGG). ZST.TO (ultra short-term) prioritized due to 2022 duration lesson.",
        "crypto_blocking": "Crypto is strictly 0% (blocking governance rule).",
        "single_equity_cap": "Single equities capped at 8% max.",
        "hyped_asset_policy_tsla": "When Robert requests TSLA, system issues an Incoherence Warning (horizon 3-5y vs TSLA vol ~58%). System proposes a constructive refusal / capped alternative of at most 3% to 5% with fixed income preserved.",
        "target_volatility": "Target volatility band 3.5% to 7.0% annualized.",
    }

    constraints = PersonaConstraints(
        target_vol_band=(0.035, 0.070),
        single_asset_cap=0.08,
        bond_floor=0.50,
        crypto_cap=0.0,
        sector_caps={},
        class_caps={
            "crypto": 0.0,
        },
        class_floors={
            "etf_bond": 0.50,
        },
        per_asset_caps={
            "ZST.TO": 0.35,
            "XBB.TO": 0.35,
            "AGG": 0.35,
        },
        exclusions=["BTC-USD", "ETH-USD", "TSLA"],
        preferred_tickers=["ZST.TO", "XBB.TO", "AGG", "RY.TO", "TD.TO", "JNJ", "PG", "FTS.TO", "XIU.TO"],
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
