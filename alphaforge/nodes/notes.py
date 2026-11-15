"""LLM notes for the three scenarios (PRD 5.7, LLM part). Owned by Track B.

Track A's scenario builder calls, after computing its scenarios and evidence:

    from alphaforge.nodes.notes import draft_notes
    scenarios = draft_notes(scenarios, evidence, profile)

One model call for the three scenarios: one or two sentences each on what the scenario trades
off, citing evidence ids. A scenario's notes are replaced only if every note passes the
verifier's id, number and wording checks; otherwise the builder's templated notes are kept.
Any model failure falls back silently to the templates.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from alphaforge import llm
from alphaforge.evidence import EID_RE, numeric
from alphaforge.nodes.verifier import check_eids, check_numbers, check_wording
from alphaforge.state import Evidence, Profile, Scenario

MAX_NOTES_PER_SCENARIO = 2


class Note(BaseModel):
    claim: str
    evidence: list[str] = Field(default_factory=list)


class ScenarioNotes(BaseModel):
    as_requested: list[Note] = Field(default_factory=list)
    capped: list[Note] = Field(default_factory=list)
    profile_baseline: list[Note] = Field(default_factory=list)


SYSTEM = (
    "Tu rédiges des notes courtes en français sur trois scénarios fictifs de portefeuille, pour un "
    "outil éducatif de simulation. Pour chaque scénario, une ou deux phrases sur ce qu'il échange "
    "(par exemple moins de perte historique contre moins d'exposition à l'idée demandée). "
    "Chaque note cite au moins un identifiant de preuve (champ evidence) pris dans la liste du "
    "scénario. Tout nombre écrit doit être recopié exactement depuis une preuve citée. "
    "Aucun conseil (jamais « achetez », « vous devriez »), aucune prévision de rendement : les "
    "indicateurs sont historiques."
)


def _fmt(ev: Evidence) -> str:
    num = numeric(ev)
    if num is None:
        return str(ev.value)
    metric = ev.value.get("metric") if isinstance(ev.value, dict) else None
    if metric == "sector_concentration_hhi":
        return f"{num:.2f}".replace(".", ",")
    return f"{num * 100:.1f} %".replace(".", ",")


def _prompt(scenarios: Sequence[Scenario], evidence: Mapping[str, Evidence], profile: Profile | None) -> str:
    lines = []
    if profile:
        lines.append(
            f"Profil : tolérance={profile.risk_tolerance}, capacité={profile.risk_capacity}, "
            f"horizon={profile.horizon_years} ans, idée={profile.requested_idea}"
        )
    for sc in scenarios:
        top = sorted(sc.weights.items(), key=lambda kv: -kv[1])[:5]
        lines.append(f"Scénario {sc.name} : " + ", ".join(f"{t} {w * 100:.1f} %".replace(".", ",") for t, w in top))
        for metric, eid in sc.metrics.items():
            if eid in evidence:
                lines.append(f"  {eid} = {_fmt(evidence[eid])} ({metric}, {evidence[eid].confidence})")
    return "\n".join(lines)


def _valid(notes: list[Note], allowed: set[str], evidence: Mapping[str, Evidence], context: list[float]) -> bool:
    if not notes or len(notes) > MAX_NOTES_PER_SCENARIO:
        return False
    for n in notes:
        cited = set(n.evidence) | set(EID_RE.findall(n.claim))
        if not cited <= allowed:
            return False
    doc = {"quelles_donnees": [n.model_dump() for n in notes]}
    return not (check_eids(doc, evidence) or check_numbers(doc, evidence, context) or check_wording(doc))


def _render(note: Note) -> str:
    ids = [e for e in note.evidence if e not in note.claim]
    return f"{note.claim.strip()} [{', '.join(ids)}]" if ids else note.claim.strip()


def _draft_scenarios(
    scenarios: list[Scenario],
    evidence: Mapping[str, Evidence],
    profile: Profile | None = None,
    *,
    llm_client=None,
) -> list[Scenario]:
    if not scenarios:
        return scenarios
    try:
        out = llm.call_json(
            _prompt(scenarios, evidence, profile),
            ScenarioNotes,
            kind="main",
            system=SYSTEM,
            llm=llm_client,
        )
    except llm.LLMError:
        return scenarios
    context = [float(w) for sc in scenarios for w in sc.weights.values()]
    if profile and profile.requested_idea:
        context.append(float(profile.requested_idea["weight"]))
    result = []
    for sc in scenarios:
        notes: list[Note] = getattr(out, sc.name, [])
        allowed = {e for e in sc.metrics.values() if e in evidence}
        if _valid(notes, allowed, evidence, context):
            sc = sc.model_copy(update={"notes": [_render(n) for n in notes]})
        result.append(sc)
    return result


def draft_notes(
    target: Scenario | Sequence[Scenario],
    evidence: Mapping[str, Evidence],
    profile: Profile | None = None,
    *,
    llm_client=None,
) -> list[str] | list[Scenario]:
    """The scenario(s) with validated LLM notes; any scenario that fails keeps its templates."""
    if isinstance(target, Scenario):
        res = _draft_scenarios([target], evidence, profile, llm_client=llm_client)
        if res and res[0].notes != target.notes:
            return res[0].notes
        return target.notes
    return _draft_scenarios(list(target), evidence, profile, llm_client=llm_client)
