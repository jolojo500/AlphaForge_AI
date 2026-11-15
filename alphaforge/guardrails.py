"""Guardrail check: every declared limit against every scenario (final report, fix 3).

Contract (orchestrator-owned signature, called at the end of scenarios_node):

    check_guardrails(profile, scenarios, evidence) -> list[dict]

Each entry:
    {
      "limit": "max_loss_12m" | "crypto_target_min" | "sector_cap" | "currency_pref"
               | "crypto_cap" | "single_stock_cap" | "account_eligibility" | "tfsa_room" | ...,
      "label_fr": str, "label_en": str,          # what the limit is, in plain words
      "scenario": "as_requested" | "capped" | "profile_baseline" | "current" | None,
      "declared": float | str | None,            # the user's limit
      "observed": float | str | None,            # the scenario's value
      "status": "ok" | "breach" | "unknown",
      "evidence": [evidence ids],                # ids of the figures compared
      "message_fr": str, "message_en": str,      # one plain sentence, no advice wording
    }
"""

from __future__ import annotations

from alphaforge.state import Evidence, Profile, Scenario


def check_guardrails(
    profile: Profile | None,
    scenarios: list[Scenario],
    evidence: dict[str, Evidence],
) -> list[dict]:
    """Stub: returns no checks until the guardrail rules are implemented."""
    return []
