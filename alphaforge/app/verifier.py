"""Deterministic Verifier for AlphaForge AI.

Guarantees 100% numerical fidelity and anti-hallucination:
- Verifies that all cited evidence IDs exist in the EvidenceRegistry.
- Extracts every numerical claim from generated explanations (quelles_donnees, pourquoi_ce_choix, alertes).
- Validates that every extracted number appears in the cited evidence item (accounting for percentages, decimals, signs, and rounding).
- Rejects hallucinated numbers or ungrounded statistics.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from alphaforge.app.evidence import EvidenceItem, EvidenceRegistry

logger = logging.getLogger(__name__)

# Regex for numbers: integers, decimals (dot or French comma), signed numbers, percentages
NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:[.,]\d+)?%?")
ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-\d{2}-\d{2}\b")


@dataclass
class VerificationError:
    section: str
    claim: str
    missing_value: str
    cited_ids: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationReport:
    is_valid: bool
    errors: list[VerificationError] = field(default_factory=list)
    total_claims_checked: int = 0
    total_numbers_verified: int = 0
    missing_evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "total_claims_checked": self.total_claims_checked,
            "total_numbers_verified": self.total_numbers_verified,
            "missing_evidence_ids": self.missing_evidence_ids,
        }


def extract_numbers_from_text(text: str) -> list[str]:
    """Extract raw numerical tokens from text, normalizing ISO dates to years."""
    # Replace ISO dates YYYY-MM-DD with just YYYY to avoid harvesting day/month digits as false metrics
    text_clean = ISO_DATE_PATTERN.sub(r"\1", text)
    tokens = NUMBER_PATTERN.findall(text_clean)
    return tokens


def parse_number_value(token: str) -> float:
    """Convert token string (e.g. '10.55%', '3,99%', '-13.01', '40') into float."""
    clean = token.strip()
    is_pct = clean.endswith("%")
    if is_pct:
        clean = clean[:-1].strip()
    # Normalize French decimal comma to dot
    clean = clean.replace(",", ".")
    val = float(clean)
    return val


def collect_numbers_from_object(obj: Any) -> set[float]:
    """Recursively harvest numbers from evidence args, results, and string metadata."""
    numbers: set[float] = set()

    if isinstance(obj, (int, float)):
        if not (np.isnan(obj) or np.isinf(obj)):
            v = float(obj)
            numbers.add(round(v, 6))
            numbers.add(round(-v, 6))
            # Also add percent scale
            numbers.add(round(v * 100.0, 4))
            numbers.add(round(-v * 100.0, 4))
    elif isinstance(obj, str):
        # Look for numbers inside strings, cleaning ISO dates first
        found = extract_numbers_from_text(obj)
        for tok in found:
            try:
                v = parse_number_value(tok)
                numbers.add(round(v, 6))
                numbers.add(round(-v, 6))
                if not tok.endswith("%"):
                    numbers.add(round(v * 100.0, 4))
                    numbers.add(round(-v * 100.0, 4))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for k, v in obj.items():
            numbers.update(collect_numbers_from_object(k))
            numbers.update(collect_numbers_from_object(v))
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            numbers.update(collect_numbers_from_object(item))

    return numbers


def build_evidence_number_pool(item: EvidenceItem) -> set[float]:
    """Extract all valid numbers supported by an evidence item."""
    pool: set[float] = set()
    pool.update(collect_numbers_from_object(item.result))
    pool.update(collect_numbers_from_object(item.args))
    pool.update(collect_numbers_from_object(item.description))
    pool.update(collect_numbers_from_object(item.date))
    return pool


def is_number_supported(target_token: str, evidence_pool: set[float], tolerance: float = 0.002) -> bool:
    """Check if target_token is present in evidence_pool within tolerance.

    Handles:
    - Decimal vs percentage equivalence (e.g. 0.1055 vs 10.55%)
    - Sign differences if contextual (e.g. drawdown -13.01% referred to as 'a 13.01% drawdown')
    - Small rounding tolerances (e.g. 3.56% vs 0.0356)
    """
    try:
        val = parse_number_value(target_token)
    except ValueError:
        return True  # Not a parseable number

    candidates = [
        val,
        -val,
        val / 100.0,
        -val / 100.0,
        val * 100.0,
        -val * 100.0,
    ]

    for cand in candidates:
        for pool_val in evidence_pool:
            if abs(cand - pool_val) <= tolerance:
                return True
            if pool_val != 0 and abs((cand - pool_val) / pool_val) <= 0.005:
                return True

    return False


def verify_explanation(
    payload: dict[str, Any],
    registry: EvidenceRegistry,
    tolerance: float = 0.002,
) -> VerificationReport:
    """Verify an explanation payload against the evidence registry.

    Validates:
    - Every cited evidence ID exists in the registry.
    - Every numeric token in claims within 'quelles_donnees', 'pourquoi_ce_choix',
      and 'alertes_gouvernance' is numerically grounded in the cited evidence.
    """
    errors: list[VerificationError] = []
    missing_ids: set[str] = set()
    claims_checked = 0
    numbers_verified = 0

    sections = [
        ("quelles_donnees", payload.get("quelles_donnees", [])),
        ("pourquoi_ce_choix", payload.get("pourquoi_ce_choix", [])),
        ("alertes_gouvernance", payload.get("alertes_gouvernance", [])),
    ]

    for section_name, items in sections:
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            claim_text = item.get("claim") or item.get("message") or ""
            cited_ids = item.get("evidence_ids", [])
            claims_checked += 1

            # 1. Verify existence of evidence IDs
            valid_items: list[EvidenceItem] = []
            for eid in cited_ids:
                if not registry.has(eid):
                    missing_ids.add(eid)
                    errors.append(
                        VerificationError(
                            section=section_name,
                            claim=claim_text,
                            missing_value=eid,
                            cited_ids=cited_ids,
                            reason=f"Cited Evidence ID '{eid}' does not exist in EvidenceRegistry.",
                        )
                    )
                else:
                    valid_items.append(registry.get(eid))

            # 2. Build number pool from all valid cited evidence
            combined_pool: set[float] = set()
            for ev_item in valid_items:
                combined_pool.update(build_evidence_number_pool(ev_item))

            # 3. Extract and verify numbers from claim
            numbers_in_claim = extract_numbers_from_text(claim_text)
            for tok in numbers_in_claim:
                if not cited_ids:
                    errors.append(
                        VerificationError(
                            section=section_name,
                            claim=claim_text,
                            missing_value=tok,
                            cited_ids=[],
                            reason=f"Numerical claim '{tok}' made without citing any Evidence ID.",
                        )
                    )
                    continue

                if not is_number_supported(tok, combined_pool, tolerance=tolerance):
                    errors.append(
                        VerificationError(
                            section=section_name,
                            claim=claim_text,
                            missing_value=tok,
                            cited_ids=cited_ids,
                            reason=f"Number '{tok}' in claim not supported by cited evidence ({', '.join(cited_ids)}).",
                        )
                    )
                else:
                    numbers_verified += 1

    is_valid = len(errors) == 0
    return VerificationReport(
        is_valid=is_valid,
        errors=errors,
        total_claims_checked=claims_checked,
        total_numbers_verified=numbers_verified,
        missing_evidence_ids=sorted(list(missing_ids)),
    )
