"""Agent 3: red team (PRD 5.8). Owned by Track B.

A hostile second reading of the three scenarios, with no tools. It looks for what rules cannot
express (hidden overlap, a "diversified" portfolio that is mostly one market, a mismatch
between the profile and a scenario). Objections must cite existing evidence ids.

Loop contract: the node returns {"retries": {"red_team": n + 1}} on every pass. A blocking
objection sends the run back to the scenario builder (bounded by MAX_RED_TEAM_LOOPS in the
graph). By default (AF_RED_TEAM_RECHECK=off), the second pass makes no model call and downgrades
objections to warnings. When AF_RED_TEAM_RECHECK=on, Sonnet re-checks the rebuilt scenarios, and
if it blocks twice, Opus decides as a tie-break. Without a model the node is a pass-through that
returns no objection.
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from alphaforge import config, llm
from alphaforge.evidence import EID_RE, numeric
from alphaforge.nodes.verifier import check_numbers, check_text_wording
from alphaforge.state import Evidence, GraphState
from alphaforge.tracing import traced

MAX_OBJECTIONS = 4
log = logging.getLogger(__name__)


class Objection(BaseModel):
    scenario: Literal["as_requested", "capped", "profile_baseline"]
    objection: str
    evidence: list[str] = Field(default_factory=list)
    severity: Literal["blocking", "warning"] = "warning"


class Review(BaseModel):
    objections: list[Objection] = Field(default_factory=list)


SYSTEM = (
    "Tu es le relecteur critique d'un outil éducatif de simulation financière. Pour chaque "
    "scénario, trouve ce qui le casse pour CETTE personne. Tu cherches ce que "
    "les règles ne voient pas : un portefeuille « diversifié » en apparence mais concentré sur un "
    "marché ou un secteur, un chevauchement d'ETF, un scénario incompatible avec l'horizon ou la "
    "capacité du profil, une donnée fictive présentée comme réelle. "
    "Réponds en français. Maximum 4 objections, seulement si elles sont solides ; sinon une liste "
    "vide. Chaque objection cite au moins un identifiant de preuve de la liste fournie et ne "
    "contient aucun nombre qui ne figure pas dans la preuve citée. "
    "severity='blocking' uniquement si le scénario contredit une contrainte ou la capacité du "
    "profil de façon que le constructeur de scénarios puisse corriger (resserrer un plafond, "
    "retirer un actif) ; sinon 'warning'. Aucun conseil, aucune prévision de rendement."
)

SYSTEM_EN = (
    "You are the red team reviewer for an educational financial simulation tool. For each "
    "scenario, find what breaks it for THIS person. You look for what "
    "the rules do not see: a superficially 'diversified' portfolio concentrated in one "
    "market or sector, ETF overlap, a scenario incompatible with the profile's horizon or "
    "capacity, fictional data presented as real. "
    "Answer in English. Maximum 4 objections, only if solid; otherwise an empty "
    "list. Each objection cites at least one evidence id from the provided list and "
    "contains no numbers that do not appear in the cited evidence. "
    "severity='blocking' only if the scenario contradicts a constraint or profile capacity in a "
    "way that the scenario builder can correct (tighten a cap, remove an asset); otherwise 'warning'. "
    "No financial advice, no return forecast."
)


def describe_evidence(ev: Evidence) -> str:
    v = ev.value
    if isinstance(v, dict):
        label = " ".join(str(v[k]) for k in ("metric", "scenario", "ticker") if k in v) or "value"
        num = numeric(ev)
        if num is None:
            body = str(v.get("value", v))
        elif v.get("unit") == "ratio":
            body = f"{num * 100:.1f} %".replace(".", ",")
        else:
            body = f"{num:.4g}"
    else:
        label, body = "valeur", str(v)
    return f"{ev.id} | {label} = {body} | {ev.source} | {ev.date} | {ev.confidence}"


def _prompt(state: GraphState, language: str = "fr") -> str:
    p = state.profile
    if language == "en":
        lines = [
            f"Profile: tolerance={p.risk_tolerance}, capacity={p.risk_capacity}, horizon={p.horizon_years} years, "
            f"constraints={p.constraints}, preferences={p.preferences}, conflicts={p.conflicts or 'none'}",
            "Scenarios:",
        ]
        for sc in state.scenarios:
            top = sorted(sc.weights.items(), key=lambda kv: -kv[1])[:8]
            shown = f"top {len(top)} of {len(sc.weights)} positions, total 100%"
            lines.append(
                f"- {sc.name} ({shown}): " + ", ".join(f"{t} {w:.0%}" for t, w in top)
                + " | metrics " + ", ".join(f"{m}={e}" for m, e in sc.metrics.items())
            )
        ids = {e for sc in state.scenarios for e in sc.metrics.values()}
        ids |= {k for k in state.evidence if k[:2] in ("ES", "EM")}
        ids |= {e["evidence_id"] for e in state.events if e.get("material")}
        lines.append("Evidence (id | indicator = value | source | date | nature):")
        lines += [describe_evidence(state.evidence[i]) for i in sorted(ids) if i in state.evidence]
        return "\n".join(lines)

    lines = [
        f"Profil : tolérance={p.risk_tolerance}, capacité={p.risk_capacity}, horizon={p.horizon_years} ans, "
        f"contraintes={p.constraints}, préférences={p.preferences}, tensions={p.conflicts or 'aucune'}",
        "Scénarios :",
    ]
    for sc in state.scenarios:
        top = sorted(sc.weights.items(), key=lambda kv: -kv[1])[:8]
        shown = f"{len(top)} premières lignes sur {len(sc.weights)}, total 100 %"
        lines.append(
            f"- {sc.name} ({shown}): " + ", ".join(f"{t} {w:.0%}" for t, w in top)
            + " | indicateurs " + ", ".join(f"{m}={e}" for m, e in sc.metrics.items())
        )
    ids = {e for sc in state.scenarios for e in sc.metrics.values()}
    ids |= {k for k in state.evidence if k[:2] in ("ES", "EM")}
    ids |= {e["evidence_id"] for e in state.events if e.get("material")}
    lines.append("Preuves (id | indicateur = valeur | source | date | nature) :")
    lines += [describe_evidence(state.evidence[i]) for i in sorted(ids) if i in state.evidence]
    return "\n".join(lines)


def reword_objection(text: str, language: str = "fr") -> str | None:
    """The objection text with internal terms replaced by their plain wording, or None when
    it still fails the wording rules after that substitution.

    Objections are shown next to the answer and checked by the verifier, but never
    regenerated: a forbidden word left here would make the explain step retry for nothing
    (#186, item 5). Plain-term substitution is deterministic; advice wording ("nous
    recommandons de vendre") has no safe rewrite and drops the objection.
    """
    from alphaforge.nodes.explain import plain_terms

    errors = check_text_wording([("objection", text)])
    if not errors:
        return text
    rewritten = plain_terms(text, language).strip()
    if rewritten != text and not check_text_wording([("objection", rewritten)]):
        log.info("red team objection reworded: %s -> %s", text, rewritten)
        return rewritten
    log.warning("red team objection dropped (wording): %s | %s", text, "; ".join(errors))
    return None


def clean_objections(review: Review, state: GraphState, first_pass: bool) -> list[dict]:
    """Keep only objections backed by existing evidence; enforce the blocking policy."""
    out = []
    language = getattr(state.profile, "language", None) or "fr"
    for o in review.objections[:MAX_OBJECTIONS]:
        ids = [e for e in dict.fromkeys(o.evidence + EID_RE.findall(o.objection)) if e in state.evidence]
        if not ids or not o.objection.strip():
            continue
        # Same deterministic checks as the explanation: no invented number, no advice wording.
        probe = {"pourquoi_ce_choix": [{"claim": o.objection, "evidence": ids}]}
        if check_numbers(probe, state.evidence):
            continue
        text = reword_objection(o.objection.strip(), language)
        if text is None:
            continue
        severity = o.severity if first_pass else "warning"
        out.append({"scenario": o.scenario, "objection": text, "evidence": ids, "severity": severity})
    return out


@traced("red_team")
def red_team_node(state: GraphState) -> dict:
    lang = getattr(state.profile, "language", None) or getattr(state, "language", "fr")
    sys = SYSTEM_EN if lang == "en" else SYSTEM
    n = state.retries.get("red_team", 0)
    update: dict = {"retries": {"red_team": n + 1}}
    if not config.RED_TEAM_ENABLED:
        return {
            **update,
            "objections": [],
            "summary": "Red team review disabled (AF_RED_TEAM=off)."
            if lang == "en"
            else "Relecture critique désactivée (AF_RED_TEAM=off).",
        }
    if not state.scenarios or state.profile is None:
        return {
            **update,
            "objections": [],
            "summary": "No objections: no scenarios to review."
            if lang == "en"
            else "Aucune objection : pas de scénario à relire.",
        }

    if n == 0:
        try:
            review = llm.call_json(_prompt(state, language=lang), Review, kind="main", system=sys)
        except llm.LLMError:
            return {
                **update,
                "objections": [],
                "summary": "Red team review unavailable: no objections."
                if lang == "en"
                else "Relecture critique indisponible : aucune objection.",
            }
        objections = clean_objections(review, state, first_pass=True)
        blocking = sum(o["severity"] == "blocking" for o in objections)
        if not objections:
            summary = (
                "No solid objections after red team review."
                if lang == "en"
                else "Aucune objection solide après relecture critique."
            )
        elif blocking:
            summary = (
                f"{len(objections)} objection(s) including {blocking} blocking: returning to scenario builder."
                if lang == "en"
                else f"{len(objections)} objection(s) dont {blocking} bloquante(s) : retour au constructeur."
            )
        else:
            summary = (
                f"{len(objections)} objection(s) raised, none blocking."
                if lang == "en"
                else f"{len(objections)} objection(s) signalée(s), aucune bloquante."
            )
        return {**update, "objections": objections, "summary": summary}

    if n > 0 and not config.RED_TEAM_RECHECK:
        # Default (#90): keep objections as warnings without a new model call to preserve latency.
        prefix = "Before revision: " if lang == "en" else "Avant révision : "
        kept = [
            {
                **o,
                "severity": "warning",
                "objection": o["objection"]
                if str(o.get("objection", "")).startswith(("Avant révision", "Before revision"))
                else f"{prefix}{o['objection']}",
            }
            for o in state.objections
        ]
        return {
            **update,
            "objections": kept,
            "summary": (
                f"Scenarios rebuilt after objection; {len(kept)} objection(s) kept as warning."
                if lang == "en"
                else f"Scénarios reconstruits après objection ; {len(kept)} objection(s) conservée(s) comme avertissement."
            ),
        }

    if n == 1:
        # Re-check with Sonnet on the rebuilt scenarios (AF_RED_TEAM_RECHECK=on)
        try:
            review = llm.call_json(_prompt(state, language=lang), Review, kind="main", system=sys)
            objections = clean_objections(review, state, first_pass=True)
            blocking = sum(o["severity"] == "blocking" for o in objections)
        except llm.LLMError:
            kept = [{**o, "severity": "warning"} for o in state.objections]
            return {
                **update,
                "objections": kept,
                "summary": "Red team review unavailable after revision; objections kept as warning."
                if lang == "en"
                else "Relecture critique indisponible après révision ; objections conservées comme avertissement.",
            }

        if blocking:
            # Sonnet returned a blocking objection twice -> Opus decides (tie-break)
            try:
                opus_review = llm.call_json(_prompt(state, language=lang), Review, kind="review", system=sys)
                opus_objections = clean_objections(opus_review, state, first_pass=False)
            except llm.LLMError:
                opus_objections = [{**o, "severity": "warning"} for o in objections]
            summary = (
                f"Opus 5.5 arbitration after two Sonnet blocks: {len(opus_objections)} objection(s) retained."
                if lang == "en"
                else f"Arbitrage Opus 5.5 après deux blocages Sonnet : {len(opus_objections)} objection(s) retenue(s)."
            )
            return {**update, "objections": opus_objections, "summary": summary}
        else:
            summary = (
                (
                    f"{len(objections)} objection(s) reported after revision, none blocking."
                    if objections
                    else "Revised scenarios validated without objection."
                )
                if lang == "en"
                else (
                    f"{len(objections)} objection(s) signalée(s) après révision, aucune bloquante."
                    if objections
                    else "Scénarios révisés validés sans objection."
                )
            )
            return {**update, "objections": objections, "summary": summary}

    # Safety fallback for n >= 2
    kept = [{**o, "severity": "warning"} for o in state.objections]
    return {
        **update,
        "objections": kept,
        "summary": (
            f"Scenarios finalized; {len(kept)} objection(s) kept as warning."
            if lang == "en"
            else f"Scénarios finalisés ; {len(kept)} objection(s) conservée(s) comme avertissement."
        ),
    }
