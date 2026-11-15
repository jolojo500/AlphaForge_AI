"""Questionnaire codes and their French labels: the one map reused by the dossier and the API.

The web questionnaire sends every answer as a code (never a French label); this module turns a
saved profile (engine keys plus questionnaire-only keys) back into labelled French lines, and
computes the dated diff appended to the dossier on every save.
"""

from __future__ import annotations

import json
from typing import Any

# Display order and French label of every field a saved profile may hold.
FIELD_LABELS_FR: dict[str, str] = {
    "profile_version": "Version du profil",
    "age_band": "Tranche d'âge",
    "family_situation": "Situation personnelle et familiale",
    "investment_knowledge": "Expérience en investissement",
    "asset_familiarity": "Actifs à l'aise d'analyser",
    "objective": "Objectif principal",
    "horizon_years": "Horizon avant retrait majeur",
    "withdrawal_plan": "Mode de décaissement",
    "budget_cad": "Capital simulé",
    "account_type": "Type de compte",
    "net_worth_share": "Part du patrimoine représentée",
    "risk_tolerance": "Tolérance au risque",
    "risk_capacity": "Capacité financière",
    "max_loss_pct": "Perte maximale tolérée sur 12 mois",
    "sector_cap_pct": "Plafond de concentration sectorielle",
    "capital_need_12m": "Besoin du capital dans les 12 mois",
    "essential_expenses_impact": "Impact d'une baisse sur les dépenses essentielles",
    "has_emergency_fund": "Fonds d'urgence",
    "debt_level": "Endettement",
    "has_high_interest_debt": "Dettes à taux élevé",
    "income_stability": "Stabilité des revenus",
    "preferences": "Secteurs et thématiques d'intérêt",
    "crypto_preference": "Place accordée aux cryptoactifs",
    "esg_level": "Critères ESG",
    "exclusions": "Exclusions spécifiques",
    "currency_preference": "Devise d'ancrage",
    "constraints": "Contraintes strictes",
    "has_existing_holdings": "Avoirs existants",
    "current_holdings": "Avoirs actuels",
    "holdings_unit": "Unité des avoirs déclarés",
    "notes": "Remarques",
}

# French label of each code, per field. A value that is not a known code is shown as typed.
VALUE_LABELS_FR: dict[str, dict[str, str]] = {
    "age_band": {"18-29": "18–29 ans", "30-44": "30–44 ans", "45-59": "45–59 ans", "60+": "60 ans et plus"},
    "family_situation": {
        "single": "Célibataire",
        "couple_no_children": "En couple (sans enfant)",
        "family_dependents": "Famille avec personnes à charge",
        "retired_independent": "Retraité / Enfants indépendants",
    },
    "investment_knowledge": {"beginner": "Débutant", "intermediate": "Intermédiaire", "advanced": "Avancé"},
    "asset_familiarity": {
        "listed_equities": "Actions cotées en bourse",
        "etfs_index": "FNB et fonds indiciels",
        "bonds_fixed_income": "Obligations et titres à revenu fixe",
        "tech_growth": "Technologies et forte croissance",
        "crypto": "Cryptoactifs et actifs numériques",
    },
    "objective": {
        "growth": "Croissance du capital",
        "balanced": "Croissance équilibrée et stabilité",
        "capital_preservation": "Préservation du capital",
        "income": "Génération de revenus réguliers",
        "project": "Financement d'un projet spécifique",
    },
    "withdrawal_plan": {
        "none": "Réinvestissement total (aucun retrait)",
        "regular_income": "Retraits progressifs périodiques",
        "lump_sum": "Décaissement unique à terme",
    },
    "account_type": {
        "tfsa": "CELI — Compte d'épargne libre d'impôt",
        "rrsp": "REER — Régime enregistré d'épargne-retraite",
        "fhsa": "CELIAPP — Compte d'épargne pour l'achat d'une première propriété",
        "non_registered": "Compte non enregistré (imposable)",
        "mixed": "Portefeuille mixte (enregistré et non enregistré)",
        "lira_rrif": "CRI / FERR — Décaissement de retraite",
        # legacy values written by earlier versions of the profile editor
        "CELI": "CELI — Compte d'épargne libre d'impôt",
        "REER": "REER — Régime enregistré d'épargne-retraite",
        "CELIAPP": "CELIAPP — Compte d'épargne pour l'achat d'une première propriété",
        "CRI": "CRI — Compte de retraite immobilisé",
    },
    "net_worth_share": {
        "lt_25": "Moins de 25 % (part modérée)",
        "25_50": "Entre 25 % et 50 % (part significative)",
        "gt_50": "Plus de 50 % (majorité du patrimoine)",
    },
    "risk_tolerance": {"low": "Faible", "low_moderate": "Faible à modéré", "moderate": "Modéré", "high": "Élevé"},
    "risk_capacity": {"low": "Faible", "moderate": "Modérée", "high": "Élevée"},
    "sector_cap_pct": {"none": "Sans plafond strict"},
    "capital_need_12m": {
        "reserve_separate": "Non, réserve d'urgence séparée",
        "need_liquidity": "Oui, une partie doit rester liquide",
        "unknown": "Indéterminé",
    },
    "essential_expenses_impact": {
        "covered": "Non, dépenses couvertes par ailleurs",
        "sensitive": "Oui, sensible aux pertes durables",
        "unknown": "Indéterminé",
    },
    "debt_level": {
        "none": "Aucune dette ou dettes remboursées",
        "mortgage_only": "Prêt hypothécaire uniquement",
        "high_interest": "Dettes à taux élevé (cartes de crédit, marge)",
    },
    "income_stability": {
        "stable": "Revenus stables (salarié permanent)",
        "variable": "Revenus variables ou travailleur autonome",
        "retired_fixed": "Retraité (revenu fixe de rente)",
    },
    "preferences": {
        "likes_tech": "Technologies et IA",
        "likes_financials": "Banques et finance",
        "likes_dividends": "Dividendes et services publics",
        "likes_healthcare": "Santé et consommation",
        "likes_bonds": "Obligations et revenu fixe",
        "likes_gold": "Or et valeurs refuges",
        "likes_energy": "Énergie et ressources",
        "likes_crypto": "Cryptoactifs",
        "esg_tilt": "Investissement responsable (ESG)",
        "wants_diversification": "Diversification",
        "wants_balance": "Équilibre",
        "wants_income": "Revenu",
        "wants_growth": "Croissance",
    },
    "crypto_preference": {
        "none": "Exclusion totale (0 % crypto)",
        "1-5": "Exposition prudente / modérée (1 à 5 %)",
        "5-15": "Favorable / ouvert (5 à 15 %)",
        "15+": "Très favorable / offensif (15 % et plus)",
    },
    "esg_level": {
        "strict": "Prioritaire — filtres stricts",
        "tilt": "Secondaire — favoriser les mieux notés",
        "neutral": "Neutre — performance financière pure",
    },
    "exclusions": {
        "fossil_fuels": "Énergies fossiles et controverses climatiques",
        "crypto": "Cryptoactifs et devises virtuelles",
    },
    "currency_preference": {
        "cad": "Priorité CAD (dollar canadien)",
        "usd": "Priorité USD (dollar américain)",
        "mixed": "Mixte CAD / USD",
        "none": "Sans contrainte de devise",
    },
    "constraints": {
        "no_crypto": "Aucun cryptoactif",
        "esg_only": "Titres ESG uniquement",
        "no_controversies": "Aucune controverse",
    },
    "has_existing_holdings": {"none": "Aucun avoir", "some": "Positions déclarées"},
    "holdings_unit": {"pct": "Pourcentage du portefeuille", "cad": "Montants en $ CAD"},
}

_BOOL_FR = {True: "Oui", False: "Non"}
_LIST_DEFAULT_FR = {
    "constraints": "Aucune contrainte stricte",
    "preferences": "Aucune préférence particulière",
    "exclusions": "Aucune",
    "asset_familiarity": "Non renseigné",
}
NOT_PROVIDED_FR = "Non renseigné"


def label_fr(key: str, value: Any) -> str:
    """French label of one answer; a code without a label is shown as typed."""
    table = VALUE_LABELS_FR.get(key, {})
    if isinstance(value, str):
        return table.get(value) or table.get(value.strip().lower()) or value
    return table.get(str(value), str(value))


def _money_fr(value: Any) -> str:
    try:
        return f"{float(value):,.0f}".replace(",", " ") + " $ CAD"
    except (TypeError, ValueError):
        return str(value)


def _pct_fr(value: Any) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if 0 < x <= 1:
        x *= 100
    return f"{x:g} %"


def format_value_fr(key: str, value: Any) -> str:
    """One answer as French text: codes become labels, numbers get their unit."""
    if value is None or value == "" or value == [] or value == {}:
        return _LIST_DEFAULT_FR.get(key, NOT_PROVIDED_FR)
    if isinstance(value, bool):
        return _BOOL_FR[value]
    if key == "budget_cad":
        return _money_fr(value)
    if key == "horizon_years":
        return f"{value} ans"
    if key == "max_loss_pct":
        return f"jusqu'à {_pct_fr(value)}"
    if key == "sector_cap_pct":
        return label_fr(key, value) if isinstance(value, str) else f"max {_pct_fr(value)} par secteur"
    if key == "net_worth_share" and not isinstance(value, str):
        return _pct_fr(value)
    if key == "profile_version":
        return f"v{value}"
    if key == "current_holdings":
        return format_holdings_fr(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(label_fr(key, v) for v in value) or _LIST_DEFAULT_FR.get(key, NOT_PROVIDED_FR)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return label_fr(key, value)


def format_holdings_fr(holdings: Any) -> str:
    """Declared holdings as "XIU.TO 40 %, SOL 10 %" (fractions and percentages) or amounts."""
    if not holdings:
        return "Aucun avoir déclaré"
    if isinstance(holdings, str):
        return holdings
    if isinstance(holdings, dict):
        parts = []
        values = [v for v in holdings.values() if isinstance(v, (int, float))]
        amounts = bool(values) and max(values) > 100
        for ticker, w in holdings.items():
            if isinstance(w, (int, float)):
                parts.append(f"{ticker} {_money_fr(w)}" if amounts else f"{ticker} {_pct_fr(w)}")
            else:
                parts.append(f"{ticker} {w}")
        return ", ".join(parts)
    try:
        return json.dumps(holdings, ensure_ascii=False)
    except Exception:
        return str(holdings)


def _flatten(profile: dict[str, Any] | None) -> dict[str, Any]:
    """A saved profile with its nested `questionnaire` answers merged in (flat keys win)."""
    out: dict[str, Any] = {}
    if not isinstance(profile, dict):
        return out
    nested = profile.get("questionnaire")
    if isinstance(nested, dict):
        out.update({k: v for k, v in nested.items() if k in FIELD_LABELS_FR})
    out.update({k: v for k, v in profile.items() if k in FIELD_LABELS_FR})
    return out


def profile_lines_fr(profile: dict[str, Any] | None, *, all_fields: bool = False) -> list[tuple[str, str]]:
    """(French label, French value) for every field of a saved profile, in questionnaire order.

    With `all_fields`, every known field appears even when unanswered ("Non renseigné").
    """
    flat = _flatten(profile)
    lines: list[tuple[str, str]] = []
    for key, label in FIELD_LABELS_FR.items():
        if key not in flat and not all_fields:
            continue
        lines.append((label, format_value_fr(key, flat.get(key))))
    return lines


def profile_summary(profile: dict[str, Any] | None) -> list[dict[str, str]]:
    """The same lines as `profile_lines_fr`, as JSON rows for the API."""
    flat = _flatten(profile)
    return [
        {"key": key, "label": FIELD_LABELS_FR[key], "value": format_value_fr(key, flat.get(key))}
        for key in FIELD_LABELS_FR
        if key in flat
    ]


def diff_profiles(old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """{field: {"old": ..., "new": ...}} for every labelled field whose value changed."""
    a, b = _flatten(old), _flatten(new)
    changes: dict[str, dict[str, Any]] = {}
    for key in FIELD_LABELS_FR:
        if key == "profile_version":
            continue
        va, vb = a.get(key), b.get(key)
        if va != vb and not (va in (None, "", [], {}) and vb in (None, "", [], {})):
            changes[key] = {"old": va, "new": vb}
    return changes


def diff_lines_fr(changes: dict[str, dict[str, Any]] | None) -> list[str]:
    """"Objectif principal : Croissance du capital → Préservation du capital" per change."""
    out = []
    for key, ch in (changes or {}).items():
        label = FIELD_LABELS_FR.get(key, key)
        out.append(f"{label} : {format_value_fr(key, ch.get('old'))} → {format_value_fr(key, ch.get('new'))}")
    return out
