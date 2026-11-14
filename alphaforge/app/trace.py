"""Observable execution trace for AlphaForge AI agentic pipeline.

Guarantees full institutional auditability and observability:
- Records structured execution events: step_start, tool_call, evidence_added, governance_alert, verification_result, done.
- Strictly excludes internal model chain-of-thought tokens (prohibited by case guidelines).
- Serializes trace to structured JSON for real-time UI streaming (Streamlit st.status) and technical documentation.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal

EventType = Literal[
    "step_start",
    "tool_call",
    "evidence_added",
    "governance_alert",
    "verification_result",
    "done",
]


@dataclass
class TraceEvent:
    """An observable, non-confidential execution event."""
    timestamp: str
    event_type: EventType
    step_name: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionTrace:
    """Collects and streams observable execution events for an analysis run."""

    def __init__(
        self,
        run_id: str | None = None,
        on_event: Callable[[TraceEvent], None] | None = None,
    ):
        self.run_id: str = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.on_event = on_event
        self.events: list[TraceEvent] = []

    def _emit(self, event_type: EventType, step_name: str, details: dict[str, Any]) -> TraceEvent:
        event = TraceEvent(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            step_name=step_name,
            details=details,
        )
        self.events.append(event)
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:
                pass  # Listener failure must not break core analysis
        return event

    def step_start(self, step_name: str, description: str = "") -> TraceEvent:
        return self._emit(
            event_type="step_start",
            step_name=step_name,
            details={"description": description},
        )

    def tool_call(self, tool: str, args: dict[str, Any], description: str = "") -> TraceEvent:
        return self._emit(
            event_type="tool_call",
            step_name=tool,
            details={"tool": tool, "args": args, "description": description},
        )

    def evidence_added(
        self, evidence_id: str, tool: str, summary: str = "", date: str = "", currency: str = ""
    ) -> TraceEvent:
        return self._emit(
            event_type="evidence_added",
            step_name="EvidenceRegistry",
            details={
                "evidence_id": evidence_id,
                "tool": tool,
                "summary": summary,
                "date": date,
                "currency": currency,
            },
        )

    def governance_alert(self, level: str, rule_id: str, message: str) -> TraceEvent:
        return self._emit(
            event_type="governance_alert",
            step_name="GovernanceEngine",
            details={"level": level, "rule_id": rule_id, "message": message},
        )

    def verification_result(
        self, is_valid: bool, num_verified: int, errors: list[dict[str, Any]] | None = None
    ) -> TraceEvent:
        return self._emit(
            event_type="verification_result",
            step_name="DeterministicVerifier",
            details={
                "is_valid": is_valid,
                "numbers_verified": num_verified,
                "errors": errors or [],
            },
        )

    def done(self, summary: str = "") -> TraceEvent:
        return self._emit(
            event_type="done",
            step_name="Pipeline",
            details={"summary": summary, "total_events": len(self.events) + 1},
        )

    def to_dict(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)
