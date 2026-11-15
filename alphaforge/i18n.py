"""Internationalization and language detection (Issue #123).

Track B owned. Supports English and French for retail investors.
"""
from __future__ import annotations

import re
from typing import Literal

Language = Literal["fr", "en"]

# Common stop words and typical tokens
_FRENCH_TOKENS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "en", "et", "ou",
    "pour", "dans", "avec", "sur", "par", "ce", "cette", "ces", "mon", "ma", "mes",
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "suis", "est", "sommes",
    "veux", "voudrais", "souhaite", "cherche", "investir", "placement", "portefeuille",
    "action", "actions", "obligation", "obligations", "titre", "titres", "fnb",
    "risque", "tolérance", "horizon", "ans", "année", "années", "perte", "rendement",
    "croissance", "préservation", "capital", "équilibré", "retraite", "prudent",
    "bonjour", "merci", "aide", "analyse", "allocation", "répartition",
}

_ENGLISH_TOKENS = {
    "the", "a", "an", "and", "or", "of", "in", "to", "for", "with", "on", "at", "by",
    "from", "this", "that", "these", "those", "my", "your", "his", "her", "its", "our",
    "their", "i", "you", "he", "she", "we", "they", "am", "is", "are", "was", "were",
    "want", "would", "like", "wish", "invest", "investing", "portfolio", "stock", "stocks",
    "bond", "bonds", "etf", "etfs", "share", "shares", "equity", "equities",
    "risk", "tolerance", "horizon", "years", "year", "yrs", "yr", "loss", "return",
    "growth", "preservation", "capital", "balanced", "retirement", "conservative",
    "hello", "hi", "please", "thanks", "help", "analyze", "analysis", "allocation",
    "build", "judge", "evaluate", "money", "cash",
}

_FRENCH_ACCENTS = re.compile(r"[éèêëàâäôöûüçîïœ]", re.IGNORECASE)


def detect_language(text: str, default: Language = "fr") -> Language:
    """Detect whether free text is English or French. Defaults to French."""
    if not text or not text.strip():
        return default

    # Extract words
    words = re.findall(r"\b[a-zA-ZÀ-ÿ]+\b", text.lower())
    if not words:
        return default

    fr_score = sum(1 for w in words if w in _FRENCH_TOKENS)
    en_score = sum(1 for w in words if w in _ENGLISH_TOKENS)

    # French accents give strong weight to French
    accents_count = len(_FRENCH_ACCENTS.findall(text))
    fr_score += accents_count * 2

    if en_score > fr_score:
        return "en"
    if fr_score > en_score:
        return "fr"

    return default
