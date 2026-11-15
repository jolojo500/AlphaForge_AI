"""Per-user dossier in S3 and local storage (PRD C-16).

Maintains a Markdown dossier per user at S3 key `users/<username>/dossier.md` (or local fallback).
Includes profile data at creation and appends profile updates and decisions.
"""

from __future__ import annotations

import abc
import datetime as dt
import hashlib
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from alphaforge import config
from alphaforge.state import GraphState

logger = logging.getLogger(__name__)

NOTICE_TEXT = (
    "> **Notice importante :** Simulation éducative, client fictif. "
    "Aucun conseil personnalisé d’investissement ni prévision de rendement. "
    "Ce document compile les hypothèses déclarées et l'historique des analyses de simulation."
)


class DossierExistsError(FileExistsError):
    """Raised when trying to create a dossier that already exists and raise_if_exists is True."""


def sanitize_username(username: str) -> str:
    """Sanitise a username for S3 keys and file paths: only [A-Za-z0-9._-].

    A name that had to be altered gets a short hash of the original appended, so two different
    usernames can never map to the same dossier.
    """
    raw = (username or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")[:64]
    if cleaned == raw and cleaned:
        return cleaned
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{cleaned or 'user'}-{digest}"


def get_dossier_s3_key(username: str) -> str:
    """Return canonical S3 key for user dossier."""
    clean = sanitize_username(username)
    return f"users/{clean}/dossier.md"


class UserDossierStore(abc.ABC):
    """Interface for dossier storage."""

    @abc.abstractmethod
    def dossier_exists(self, username: str) -> bool:
        """Check if user dossier exists."""

    @abc.abstractmethod
    def read_dossier(self, username: str) -> str | None:
        """Read user dossier Markdown content, or None if not found."""

    @abc.abstractmethod
    def write_dossier(self, username: str, content: str) -> None:
        """Write user dossier Markdown content."""


class LocalUserDossierStore(UserDossierStore):
    """Local-file dossier storage under the existing local data directory."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        if storage_dir is None:
            self.storage_dir = Path(os.getenv("AF_DOSSIER_DIR", config.REPO_ROOT / "data"))
        else:
            self.storage_dir = Path(storage_dir)

    def _file_path(self, username: str) -> Path:
        clean = sanitize_username(username)
        return self.storage_dir / "users" / clean / "dossier.md"

    def dossier_exists(self, username: str) -> bool:
        return self._file_path(username).is_file()

    def read_dossier(self, username: str) -> str | None:
        p = self._file_path(username)
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8")

    def write_dossier(self, username: str, content: str) -> None:
        p = self._file_path(username)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def _is_missing(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    code = str(resp.get("Error", {}).get("Code", "")) if isinstance(resp, dict) else ""
    return code in ("404", "NoSuchKey", "NotFound")


class S3UserDossierStore(UserDossierStore):
    """S3-backed dossier storage.

    Only "object not found" means the dossier is missing. Any other S3 error is raised: treating
    an outage as "no dossier" would recreate the file and erase the user's history. The local
    store is used only when no bucket is configured.
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        region_name: str | None = None,
        s3_client: Any = None,
        local_fallback: LocalUserDossierStore | None = None,
    ) -> None:
        self.bucket_name = bucket_name or config.S3_BUCKET
        self.region_name = region_name or config.AWS_REGION
        self.fallback = local_fallback or LocalUserDossierStore()

        if s3_client is not None:
            self._s3 = s3_client
        elif self.bucket_name:
            import boto3

            profile = os.getenv("AWS_PROFILE")
            if profile:
                session = boto3.Session(profile_name=profile, region_name=self.region_name)
            else:
                session = boto3.Session(region_name=self.region_name)
            self._s3 = session.client("s3", region_name=self.region_name)
        else:
            self._s3 = None

    @property
    def _use_s3(self) -> bool:
        return self._s3 is not None and bool(self.bucket_name)

    def dossier_exists(self, username: str) -> bool:
        if not self._use_s3:
            return self.fallback.dossier_exists(username)
        try:
            self._s3.head_object(Bucket=self.bucket_name, Key=get_dossier_s3_key(username))
            return True
        except Exception as exc:
            if _is_missing(exc):
                return False
            raise

    def read_dossier(self, username: str) -> str | None:
        if not self._use_s3:
            return self.fallback.read_dossier(username)
        try:
            resp = self._s3.get_object(Bucket=self.bucket_name, Key=get_dossier_s3_key(username))
        except Exception as exc:
            if _is_missing(exc):
                return None
            raise
        body = resp["Body"].read()
        return body.decode("utf-8") if isinstance(body, bytes) else str(body)

    def write_dossier(self, username: str, content: str) -> None:
        if not self._use_s3:
            self.fallback.write_dossier(username, content)
            return
        self._s3.put_object(
            Bucket=self.bucket_name,
            Key=get_dossier_s3_key(username),
            Body=content.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
        )


# One writer at a time: appends are read-modify-write on a single object.
_write_lock = threading.Lock()

_global_dossier_store: UserDossierStore | None = None


def get_dossier_store() -> UserDossierStore:
    """Factory returning active UserDossierStore (S3 with local fallback or Local)."""
    global _global_dossier_store
    if _global_dossier_store is not None:
        return _global_dossier_store

    backend = os.getenv("AF_DOSSIER_BACKEND")
    if not backend:
        if "PYTEST_CURRENT_TEST" in os.environ or os.getenv("AF_AUTH") == "off" or not config.S3_BUCKET:
            backend = "local"
        else:
            backend = "s3"

    if backend == "s3":
        try:
            _global_dossier_store = S3UserDossierStore()
        except Exception:
            logger.warning("Falling back to LocalUserDossierStore")
            _global_dossier_store = LocalUserDossierStore()
    else:
        _global_dossier_store = LocalUserDossierStore()

    return _global_dossier_store


def set_dossier_store_override(store: UserDossierStore | None) -> None:
    """Set global dossier store override (for unit testing)."""
    global _global_dossier_store
    _global_dossier_store = store


# --- Markdown formatting helpers ----------------------------------------------------


def _get_val(obj: Any, *keys: str, default: Any = "Non renseigné") -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] is not None and obj[k] != "":
                return obj[k]
        nested = obj.get("profile")
        if isinstance(nested, dict):
            for k in keys:
                if k in nested and nested[k] is not None and nested[k] != "":
                    return nested[k]
        return default
    for k in keys:
        if hasattr(obj, k):
            val = getattr(obj, k)
            if val is not None and val != "":
                return val
    return default


def _format_holdings(holdings: Any) -> str:
    if not holdings:
        return "Aucun avoir initial déclaré"
    if isinstance(holdings, str):
        return holdings
    try:
        return json.dumps(holdings, indent=2, ensure_ascii=False)
    except Exception:
        return str(holdings)


def _format_list(items: Any, default: str = "Aucune") -> str:
    if not items:
        return default
    if isinstance(items, list):
        if not items:
            return default
        return ", ".join(str(x) for x in items)
    return str(items)


def _build_initial_dossier(
    username: str,
    email: str | None,
    profile: dict[str, Any],
    created_at: str,
) -> str:
    clean_username = sanitize_username(username)
    email_display = email or _get_val(profile, "email", default="Non renseigné")

    objective = _get_val(profile, "objective")
    horizon = _get_val(profile, "horizon_years", "horizon")
    if horizon != "Non renseigné":
        horizon = f"{horizon} ans"
    tolerance = _get_val(profile, "risk_tolerance", "tolerance")
    capacity = _get_val(profile, "risk_capacity", "capacity")
    budget = _get_val(profile, "budget_cad", "budget")
    if budget != "Non renseigné":
        budget = f"{budget} CAD"
    account_type = _get_val(profile, "account_type")
    constraints = _format_list(_get_val(profile, "constraints", default=[]), default="Aucune contrainte stricte")
    preferences = _format_list(_get_val(profile, "preferences", default=[]), default="Aucune préférence particulière")
    holdings = _format_holdings(_get_val(profile, "current_holdings", "holdings", default=None))
    notes = _get_val(profile, "notes", default="Aucune note")

    lines = [
        f"# Dossier d'investisseur : {clean_username}",
        "",
        NOTICE_TEXT,
        "",
        f"- **Utilisateur :** {clean_username}",
        f"- **Courriel :** {email_display}",
        f"- **Date de création (UTC) :** {created_at}",
        "",
        "## Profil à la création",
        "",
        f"- **Objectif :** {objective}",
        f"- **Horizon :** {horizon}",
        f"- **Tolérance au risque :** {tolerance}",
        f"- **Capacité de risque :** {capacity}",
        f"- **Budget :** {budget}",
        f"- **Type de compte :** {account_type}",
        f"- **Contraintes :** {constraints}",
        f"- **Préférences :** {preferences}",
        f"- **Avoirs actuels :** {holdings}",
        f"- **Notes :** {notes}",
    ]
    return "\n".join(lines)


def _build_profile_update_section(profile: dict[str, Any], updated_at: str) -> str:
    objective = _get_val(profile, "objective")
    horizon = _get_val(profile, "horizon_years", "horizon")
    if horizon != "Non renseigné":
        horizon = f"{horizon} ans"
    tolerance = _get_val(profile, "risk_tolerance", "tolerance")
    capacity = _get_val(profile, "risk_capacity", "capacity")
    budget = _get_val(profile, "budget_cad", "budget")
    if budget != "Non renseigné":
        budget = f"{budget} CAD"
    account_type = _get_val(profile, "account_type")
    constraints = _format_list(_get_val(profile, "constraints", default=[]), default="Aucune contrainte stricte")
    preferences = _format_list(_get_val(profile, "preferences", default=[]), default="Aucune préférence particulière")
    holdings = _format_holdings(_get_val(profile, "current_holdings", "holdings", default=None))
    notes = _get_val(profile, "notes", default="Aucune note")

    lines = [
        f"## Mise à jour du profil — {updated_at}",
        "",
        f"- **Objectif :** {objective}",
        f"- **Horizon :** {horizon}",
        f"- **Tolérance au risque :** {tolerance}",
        f"- **Capacité de risque :** {capacity}",
        f"- **Budget :** {budget}",
        f"- **Type de compte :** {account_type}",
        f"- **Contraintes :** {constraints}",
        f"- **Préférences :** {preferences}",
        f"- **Avoirs actuels :** {holdings}",
        f"- **Notes :** {notes}",
    ]
    return "\n".join(lines)


def _extract_metric_evidence_val(ev_item: Any) -> str:
    if not ev_item:
        return ""
    if isinstance(ev_item, dict):
        val = ev_item.get("value")
    elif hasattr(ev_item, "value"):
        val = ev_item.value
    else:
        val = ev_item

    if isinstance(val, dict):
        num = val.get("value")
        unit = val.get("unit")
        if unit == "ratio" and isinstance(num, (int, float)):
            return f"{num:.4f} ({num * 100:.2f}%)"
        return str(num)
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)


def _build_decision_section(
    run_state: GraphState | dict[str, Any],
    run_id: str | None,
    decision_at: str,
) -> str:
    rid = run_id or _get_val(run_state, "run_id", default="inconnu")
    request_text = _get_val(run_state, "request_text", default="")
    as_of_date = _get_val(run_state, "as_of_date", default="")

    profile = _get_val(run_state, "profile", default=None)
    conflicts: list[str] = []
    if profile:
        conflicts = _get_val(profile, "conflicts", default=[]) or []

    lines = [
        f"## Décision et simulation — {decision_at}",
        "",
        f"- **Identifiant de simulation (run_id) :** `{rid}`",
        f"- **Date de référence des données (as_of_date) :** {as_of_date}",
        f"- **Demande / Question de l'investisseur :** {request_text}",
        "",
        "### Profil résolu et cohérence",
        "",
    ]

    if profile:
        objective = _get_val(profile, "objective")
        horizon = _get_val(profile, "horizon_years", "horizon")
        if horizon != "Non renseigné":
            horizon = f"{horizon} ans"
        tolerance = _get_val(profile, "risk_tolerance", "tolerance")
        capacity = _get_val(profile, "risk_capacity", "capacity")
        budget = _get_val(profile, "budget_cad", "budget")
        if budget != "Non renseigné":
            budget = f"{budget} CAD"
        account_type = _get_val(profile, "account_type")
        constraints = _format_list(_get_val(profile, "constraints", default=[]), default="Aucune")
        preferences = _format_list(_get_val(profile, "preferences", default=[]), default="Aucune")

        lines.extend([
            f"- **Objectif :** {objective}",
            f"- **Horizon :** {horizon}",
            f"- **Tolérance au risque :** {tolerance}",
            f"- **Capacité de risque :** {capacity}",
            f"- **Budget :** {budget}",
            f"- **Type de compte :** {account_type}",
            f"- **Contraintes :** {constraints}",
            f"- **Préférences :** {preferences}",
        ])
    else:
        lines.append("- Aucun profil formellement attaché.")

    lines.append("")
    lines.append("#### Conflits identifiés")
    if conflicts:
        for c in conflicts:
            lines.append(f"- {c}")
    else:
        lines.append("Aucun conflit identifié entre la demande et le profil.")

    # Scenarios
    scenarios = _get_val(run_state, "scenarios", default=[]) or []
    evidence_dict = _get_val(run_state, "evidence", default={}) or {}

    lines.append("")
    lines.append("### Scénarios comparés")
    lines.append("")

    for s in scenarios:
        s_name = _get_val(s, "name", default="scénario")
        s_weights = _get_val(s, "weights", default={}) or {}
        s_metrics = _get_val(s, "metrics", default={}) or {}

        lines.append(f"#### Scénario : `{s_name}`")
        lines.append("")
        lines.append("**Pondération des actifs :**")
        if s_weights:
            lines.append("| Actif | Poids |")
            lines.append("| :--- | :--- |")
            for ticker, w in s_weights.items():
                try:
                    pct = float(w) * 100.0
                    lines.append(f"| {ticker} | {pct:.2f}% ({float(w):.4f}) |")
                except Exception:
                    lines.append(f"| {ticker} | {w} |")
        else:
            lines.append("Aucune pondération enregistrée.")
        lines.append("")

        lines.append("**Indicateurs clés et preuves :**")
        if s_metrics:
            for m_name, ev_id in s_metrics.items():
                ev_obj = evidence_dict.get(ev_id) if isinstance(evidence_dict, dict) else None
                formatted_val = _extract_metric_evidence_val(ev_obj)
                if formatted_val:
                    lines.append(f"- **{m_name} :** {formatted_val} (Preuve `{ev_id}`)")
                else:
                    lines.append(f"- **{m_name} :** Preuve `{ev_id}`")
        else:
            lines.append("Aucun indicateur chiffré.")
        lines.append("")

    # Scenario most consistent & explanation
    explanation = _get_val(run_state, "explanation", default={}) or {}
    most_consistent = (
        _get_val(explanation, "scenario_le_plus_coherent", "most_consistent_scenario", default=None)
        or _get_val(run_state, "chosen_scenario", default=None)
    )

    lines.append("### Scénario jugé le plus cohérent")
    if most_consistent:
        lines.append(f"**Scénario :** `{most_consistent}`")
    else:
        lines.append("Non déterminé.")
    lines.append("")

    resume = _get_val(explanation, "resume", default=None)
    lines.append("### Synthèse vérifiée de l'explication")
    if resume:
        lines.append(f"{resume}")
    else:
        lines.append("Aucun résumé d'explication disponible.")
    lines.append("")

    # Exclusions
    exclusions = _get_val(run_state, "exclusions", default=[]) or []
    lines.append("### Exclusions de l'univers d'investissement")
    if exclusions:
        for ex in exclusions:
            ticker = _get_val(ex, "ticker", default="?")
            reason = _get_val(ex, "reason", default="Exclu par les règles de filtrage")
            ev_id = _get_val(ex, "evidence_id", default=None)
            ev_suffix = f" (Preuve `{ev_id}`)" if ev_id else ""
            lines.append(f"- **{ticker}** : {reason}{ev_suffix}")
    else:
        lines.append("Aucun actif exclu pour ce profil.")
    lines.append("")

    # Verifier result
    verification = _get_val(run_state, "verification", default={}) or {}
    passed = _get_val(verification, "passed", default=False)
    lines.append("### Résultat du vérificateur formel déterministe")
    if passed:
        lines.append("- **Statut :** Conforme (intégrité des chiffres et conformité non-conseil validées)")
    else:
        errors = _get_val(verification, "errors", default=[]) or []
        err_msg = ", ".join(str(e) for e in errors) if errors else "Échec de validation formelle"
        lines.append(f"- **Statut :** Non conforme ({err_msg})")
    lines.append("")

    # Advisor review / sign-off (when present)
    reviewed = _get_val(run_state, "reviewed", default=False)
    reviewer_id = _get_val(run_state, "reviewer_id", default=None)
    if reviewed or reviewer_id:
        reviewed_at = _get_val(run_state, "reviewed_at", default="Date non enregistrée")
        chosen = _get_val(run_state, "chosen_scenario", default="Non spécifié")
        rationale = _get_val(run_state, "advisor_rationale", default="Aucune justification saisie")
        edited = _get_val(run_state, "edited_assumptions", default=None)

        lines.append("### Révision et signature du conseiller")
        lines.append(f"- **Conseiller réviseur :** {reviewer_id}")
        lines.append(f"- **Date de révision (UTC) :** {reviewed_at}")
        lines.append(f"- **Scénario retenu :** `{chosen}`")
        lines.append(f"- **Justification professionnelle :** {rationale}")
        if edited:
            lines.append(f"- **Hypothèses modifiées :** {json.dumps(edited, ensure_ascii=False)}")
        lines.append("")

    return "\n".join(lines)


# --- Public API functions -----------------------------------------------------------


def _create_dossier_unlocked(
    username: str,
    email: str | None = None,
    profile: dict[str, Any] | None = None,
    raise_if_exists: bool = False,
) -> str:
    """Create a new user dossier Markdown file in S3 or local fallback.

    Writes header, 'simulation éducative, client fictif' notice, and 'Profil à la création' section.
    Never overwrites an existing dossier.
    """
    store = get_dossier_store()
    if store.dossier_exists(username):
        existing = store.read_dossier(username)
        if existing:
            if raise_if_exists:
                raise DossierExistsError(f"Dossier for user '{username}' already exists")
            logger.info("Dossier for user '%s' already exists; skipping overwrite.", username)
            return existing

    now_utc = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    content = _build_initial_dossier(
        username=username,
        email=email,
        profile=profile or {},
        created_at=now_utc,
    )
    store.write_dossier(username, content)
    return content


def _append_profile_update_unlocked(username: str, profile: dict[str, Any]) -> str:
    """Append a dated 'Mise à jour du profil' section to the user's dossier (creates if missing)."""
    store = get_dossier_store()
    existing = store.read_dossier(username)
    if not existing:
        return _create_dossier_unlocked(username=username, profile=profile)

    now_utc = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    section = _build_profile_update_section(profile=profile, updated_at=now_utc)
    new_content = existing.rstrip() + "\n\n---\n\n" + section + "\n"
    store.write_dossier(username, new_content)
    return new_content


def _append_decision_unlocked(
    username: str,
    run_state: GraphState | dict[str, Any],
    run_id: str | None = None,
) -> str:
    """Append a dated finished run decision section to the user's dossier (creates if missing).

    Includes run id, question, resolved profile + conflicts, the 3 scenarios (weights and key metrics
    with evidence ids), scenario judged most consistent, verified explanation.resume, exclusions,
    verifier result, and advisor review when present.
    """
    store = get_dossier_store()
    existing = store.read_dossier(username)
    if not existing:
        # Create initial dossier first if none exists
        prof_dict = {}
        state_prof = _get_val(run_state, "profile", default=None)
        if state_prof:
            prof_dict = state_prof if isinstance(state_prof, dict) else state_prof.model_dump(mode="json")
        existing = _create_dossier_unlocked(username=username, profile=prof_dict)

    now_utc = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    decision_section = _build_decision_section(
        run_state=run_state,
        run_id=run_id,
        decision_at=now_utc,
    )
    new_content = existing.rstrip() + "\n\n---\n\n" + decision_section + "\n"
    store.write_dossier(username, new_content)
    return new_content


def create_dossier(
    username: str,
    email: str | None = None,
    profile: dict[str, Any] | None = None,
    raise_if_exists: bool = False,
) -> str:
    """Create the dossier (header, notice, profile at creation). Never overwrites an existing one."""
    with _write_lock:
        return _create_dossier_unlocked(username, email, profile, raise_if_exists)


def append_profile_update(username: str, profile: dict[str, Any]) -> str:
    """Append a dated profile update (creates the dossier if missing)."""
    with _write_lock:
        return _append_profile_update_unlocked(username, profile)


def append_decision(
    username: str,
    run_state: GraphState | dict[str, Any],
    run_id: str | None = None,
) -> str:
    """Append a dated section for a finished run (creates the dossier if missing)."""
    with _write_lock:
        return _append_decision_unlocked(username, run_state, run_id)


def read_dossier(username: str) -> str | None:
    """Read the Markdown content of the user's dossier, or None if it does not exist."""
    store = get_dossier_store()
    return store.read_dossier(username)
