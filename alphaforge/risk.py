"""Risk scale shared by profile conflicts and scenario caps (B-12).

Suitability follows the more conservative of what the client says they accept (tolerance)
and what their situation can absorb (capacity), as under CIRO rules.
"""

from __future__ import annotations

# Ordered from most conservative to least. Capacity only uses low/moderate/high.
RISK_LEVELS: tuple[str, ...] = ("low", "low_moderate", "moderate", "high")


def risk_index(level: str) -> int:
    """Position of a risk level; an unknown level is treated as moderate."""
    try:
        return RISK_LEVELS.index(level)
    except ValueError:
        return RISK_LEVELS.index("moderate")


def effective_risk(tolerance: str, capacity: str) -> str:
    """The more conservative of stated tolerance and actual capacity."""
    return min(tolerance, capacity, key=risk_index)


def risk_gap(tolerance: str, capacity: str) -> int:
    """Number of levels between tolerance and capacity."""
    return abs(risk_index(tolerance) - risk_index(capacity))


def binding_risk(tolerance: str, capacity: str) -> str:
    """Which side sets the effective limit: `tolerance`, `capacity`, or `both`."""
    tolerance_i, capacity_i = risk_index(tolerance), risk_index(capacity)
    if tolerance_i == capacity_i:
        return "both"
    return "capacity" if capacity_i < tolerance_i else "tolerance"
