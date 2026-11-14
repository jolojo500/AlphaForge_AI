"""Evidence registry and traceable audit trail for AlphaForge AI.

Guarantees institutional transparency and explainability:
- Every quantitative claim made by the solution or agents must reference a registered Evidence ID (E1..En).
- Each evidence record captures: tool, arguments, exact result, data source, date, currency, and description.
- The verifier validates that downstream outputs never cite non-existent evidence or invent unsupported numbers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass
class EvidenceItem:
    id: str  # E1, E2, ...
    tool: str
    args: dict[str, Any]
    result: Any
    source: str
    date: str
    currency: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceRegistry:
    """Sequential registry of deterministic execution evidence."""

    def __init__(self, default_currency: str = "CAD", default_source: str = "PolyFinances Starter / AlphaForge Engine"):
        self.default_currency = default_currency
        self.default_source = default_source
        self._items: dict[str, EvidenceItem] = {}
        self._counter: int = 1

    def register(
        self,
        tool: str,
        args: dict[str, Any],
        result: Any,
        source: str | None = None,
        date_str: str | None = None,
        currency: str | None = None,
        description: str = "",
    ) -> EvidenceItem:
        """Register a new deterministic tool execution as an evidence record."""
        eid = f"E{self._counter}"
        self._counter += 1

        item = EvidenceItem(
            id=eid,
            tool=tool,
            args=args,
            result=result,
            source=source or self.default_source,
            date=date_str or "2026-11-13",
            currency=currency or self.default_currency,
            description=description,
        )
        self._items[eid] = item
        return item

    def get(self, eid: str) -> EvidenceItem:
        """Retrieve evidence item by its ID (e.g., 'E1')."""
        if eid not in self._items:
            raise KeyError(f"Evidence ID '{eid}' does not exist in registry. Available: {list(self._items.keys())}")
        return self._items[eid]

    def has(self, eid: str) -> bool:
        """Check whether an evidence ID exists."""
        return eid in self._items

    def list_all(self) -> list[EvidenceItem]:
        """Return all registered evidence items in order."""
        return list(self._items.values())

    def clear(self) -> None:
        """Reset the registry."""
        self._items.clear()
        self._counter = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize all evidence items to dictionary."""
        return {eid: item.to_dict() for eid, item in self._items.items()}

    def to_json(self, indent: int = 2) -> str:
        """Export evidence registry as formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
