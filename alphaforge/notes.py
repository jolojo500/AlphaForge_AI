"""Scenario notes (PRD 5.7, LLM part). Owned by Track B.

Track A's scenario builder calls:

    from alphaforge.notes import draft_notes
    notes = draft_notes(scenario, evidence, profile)

The model writes up to 3 short French notes. Each note cites evidence ids and contains no
number of its own. Anything that fails validation is replaced by templated notes built
directly from the evidence, so the builder always gets usable text.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import BaseModel, Field

from alphaforge import llm
from alphaforge.evidence import EID_RE, numeric
from alphaforge.state import SCENARIO_METRICS, Evidence, Profile, Scenario

MAX_NOTES = 3
LABELS = {
    "volatility_ann": "Volatilité annualisée historique",
    "max_drawdown": "Perte maximale historique",
    "stress_2022": "Résultat historique du stress de 2022",
    "top_weight": "Poids de la plus grosse position",
    "sector_concentration_hhi": "Concentration sectorielle (HHI)",
    "us_exposure": "Exposition aux États-Unis",
}
_PERCENT_METRICS = {"volatility_ann", "max_drawdown", "stress_2022", "top_weight", "us_exposure"}


class Notes(BaseModel):
    notes: list[str] = Field(default_factory=list)


SYSTEM = (
    "Tu rédiges des notes courtes (une phrase chacune, en français) sur un scénario fictif de "
    "portefeuille, pour un outil éducatif. Maximum 3 notes. Chaque note cite au moins un "
    "identifiant de preuve entre crochets, par exemple [EP3], pris dans la liste fournie. "
    "N'écris AUCUN nombre : renvoie le lecteur à l'identifiant. Pas de conseil (jamais "
    "« achetez », « vous devriez »), aucune prévision de rendement : les indicateurs sont "
    "historiques. Décris ce que le scénario montre et ce qu'il ne montre pas."
)


def _fmt(metric: str, ev: Evidence) -> str:
    v = numeric(ev)
    if v is None:
        return str(ev.value)
    if metric == "sector_concentration_hhi":
        return f"{v:.2f}"
    return f"{abs(v):.1%}" if metric in _PERCENT_METRICS else f"{v:.3g}"


def template_notes(scenario: Scenario, evidence: Mapping[str, Evidence]) -> list[str]:
    """Deterministic notes: one line per metric available, each with its evidence id."""
    notes = []
    for metric in SCENARIO_METRICS:
        eid = scenario.metrics.get(metric)
        if eid and eid in evidence:
            notes.append(f"{LABELS[metric]} : {_fmt(metric, evidence[eid])} [{eid}].")
    caveat = "Scénario fictif fondé sur des statistiques historiques, sans prévision de rendement."
    return (notes[:5] + [caveat]) if notes else [caveat]


def _valid(note: str, allowed: set[str], evidence: Mapping[str, Evidence]) -> bool:
    ids = EID_RE.findall(note)
    if not ids or any(i not in evidence for i in ids):
        return False
    if not set(ids) <= allowed:
        return False
    if re.search(r"\d", EID_RE.sub("", note)):  # the model must not write numbers
        return False
    try:
        from alphaforge.nodes.verifier import check_wording
    except ImportError:  # verifier not merged yet
        return True
    return not check_wording({"resume": note})


def _prompt(scenario: Scenario, evidence: Mapping[str, Evidence], profile: Profile | None) -> str:
    top = sorted(scenario.weights.items(), key=lambda kv: -kv[1])[:6]
    lines = [
        f"Scénario : {scenario.name}",
        "Positions principales : " + ", ".join(f"{t} {w:.0%}" for t, w in top),
    ]
    if profile:
        lines.append(
            f"Profil : tolérance={profile.risk_tolerance}, horizon={profile.horizon_years} ans, "
            f"contraintes={profile.constraints}"
        )
    lines.append("Preuves (id | indicateur = valeur | nature) :")
    for metric, eid in scenario.metrics.items():
        if eid in evidence:
            ev = evidence[eid]
            lines.append(f"{eid} | {LABELS.get(metric, metric)} = {_fmt(metric, ev)} | {ev.confidence}")
    return "\n".join(lines)


def draft_notes(
    scenario: Scenario,
    evidence: Mapping[str, Evidence],
    profile: Profile | None = None,
    *,
    llm_client=None,
) -> list[str]:
    """Up to 3 validated notes citing evidence ids, or templated notes if the model fails."""
    allowed = {e for e in scenario.metrics.values() if e in evidence}
    if not allowed:
        return template_notes(scenario, evidence)
    try:
        out = llm.call_json(
            _prompt(scenario, evidence, profile), Notes, kind="main", system=SYSTEM, llm=llm_client
        )
    except llm.LLMError:
        return template_notes(scenario, evidence)
    notes = [n.strip() for n in out.notes if n.strip()][:MAX_NOTES]
    if not notes or not all(_valid(n, allowed, evidence) for n in notes):
        return template_notes(scenario, evidence)
    return notes
