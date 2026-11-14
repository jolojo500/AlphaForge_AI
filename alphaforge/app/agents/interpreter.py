"""Natural Language Request Interpreter Agent for AlphaForge AI.

Interprets free-form investor queries (in French or English) into structured requests:
- Targets fast, lightweight Claude Haiku 3.5 (global.anthropic.claude-haiku-5-5).
- Maps colloquial asset and company names to universe tickers using assets_universe.csv:
    e.g. "Tesla" -> TSLA, "Bitcoin" / "Crypto" -> BTC-USD, "Enbridge" -> ENB.TO.
- Extracts requested allocation weights (e.g. "20%", "la moitié" -> 0.20, 0.50).
- Flags out-of-scope requests (options, leverage, penny stocks, guaranteed returns).
- Emits observable trace events and registers parsed request into EvidenceRegistry.
- Includes a robust deterministic regex fallback for offline resilience.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import pandas as pd

from alphaforge.app.bedrock import BedrockConverseClient, MODEL_HAIKU
from alphaforge.app.evidence import EvidenceRegistry
from alphaforge.app.schemas import ParsedRequest, RequestedPosition
from alphaforge.app.trace import ExecutionTrace

logger = logging.getLogger(__name__)

# Known company / asset name aliases to canonical tickers in universe
COMPANY_TICKER_MAP = {
    "tesla": "TSLA",
    "tesla motors": "TSLA",
    "tsla": "TSLA",
    "bitcoin": "BTC-USD",
    "btc": "BTC-USD",
    "crypto": "BTC-USD",
    "cryptomonnaie": "BTC-USD",
    "cryptomonnaies": "BTC-USD",
    "ethereum": "ETH-USD",
    "eth": "ETH-USD",
    "ether": "ETH-USD",
    "enbridge": "ENB.TO",
    "enb": "ENB.TO",
    "apple": "AAPL",
    "aapl": "AAPL",
    "microsoft": "MSFT",
    "msft": "MSFT",
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "amazon": "AMZN",
    "amzn": "AMZN",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "googl": "GOOGL",
    "goog": "GOOGL",
    "canadian natural": "CNQ.TO",
    "cnq": "CNQ.TO",
    "cn rail": "CNR.TO",
    "cnr": "CNR.TO",
    "canadian national": "CNR.TO",
    "royal bank": "RY.TO",
    "rbc": "RY.TO",
    "ry": "RY.TO",
    "td": "TD.TO",
    "td bank": "TD.TO",
    "toronto-dominion": "TD.TO",
    "manulife": "MFC.TO",
    "mfc": "MFC.TO",
    "fortis": "FTS.TO",
    "fts": "FTS.TO",
    "couche-tard": "ATD.TO",
    "atd": "ATD.TO",
    "shopify": "SHOP.TO",
    "shop": "SHOP.TO",
    "constellation": "CSU.TO",
    "csu": "CSU.TO",
    "jpmorgan": "JPM",
    "jpm": "JPM",
    "johnson & johnson": "JNJ",
    "jnj": "JNJ",
    "procter & gamble": "PG",
    "pg": "PG",
    "exxon": "XOM",
    "exxon mobil": "XOM",
    "xom": "XOM",
    "gold": "GLD",
    "or": "GLD",
    "gld": "GLD",
    "s&p 500": "SPY",
    "spy": "SPY",
    "nasdaq": "QQQ",
    "qqq": "QQQ",
    "tsx": "XIU.TO",
    "xiu": "XIU.TO",
    "esg": "ESGV",
    "esgv": "ESGV",
    "vanguard esg": "ESGV",
    "obligations": "XBB.TO",
    "bonds": "AGG",
    "treasury": "TLT",
    "tlt": "TLT",
    "zst": "ZST.TO",
    "xbb": "XBB.TO",
    "agg": "AGG",
}

PERCENT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|pourcent|pour\s*cent)", re.IGNORECASE)

INTERPRETER_SYSTEM_PROMPT = """Tu es l'Interpréteur de Requêtes en Langage Naturel d'AlphaForge AI pour le courtage direct (BNCD).
Ton rôle est d'analyser la question ou la demande formulée par l'investisseur et d'en extraire les entités et intentions financières.

RÈGLES D'EXTRACTION STRICTES :
1. MAPPING DES TICKERS : Associe chaque entreprise ou actif mentionné à son ticker officiel dans l'univers :
   - Tesla -> TSLA
   - Bitcoin / Cryptos -> BTC-USD (et/ou ETH-USD)
   - Enbridge -> ENB.TO
   - Apple -> AAPL, Microsoft -> MSFT, NVIDIA -> NVDA, Amazon -> AMZN, Alphabet/Google -> GOOGL
   - Canadian Natural Resources -> CNQ.TO, Fortis -> FTS.TO, Royal Bank -> RY.TO, TD -> TD.TO
   - FNB : SPY (S&P 500), QQQ (Nasdaq), XIU.TO (TSX 60), ESGV (ESG), XBB.TO / AGG / ZST.TO (Obligations), GLD (Or).
2. EXTRACTION DU POIDS SOUHAITÉ : Si l'utilisateur mentionne un pourcentage (ex: "20%", "15 pourcent", "la moitié" -> 0.50), convertis-le en nombre décimal (ex: 0.20). Si aucun pourcentage n'est précisé, indique null.
3. ACTIFS HORS UNIVERS : Si l'utilisateur demande une action non répertoriée (ex: GameStop, Dogecoin, micro-caps), place-la dans 'unknown_entities' et mets 'out_of_scope: true'. Ne JAMAIS inventer un ticker.
4. HORS MANDAT : Mets 'out_of_scope: true' si la demande concerne des options, du levier, des conseils fiscaux, ou une exécution réelle d'ordres.
5. FORMAT DE SORTIE : Réponds STRICTEMENT en format JSON valide conforme au schéma :

```json
{
  "intent": "add_position" | "screen_esg" | "risk_query" | "general_allocation" | "out_of_scope",
  "requested_positions": [
    {"ticker": "TSLA", "weight": 0.20, "company_name": "Tesla"}
  ],
  "requested_exclusions": [],
  "constraint_changes": {},
  "out_of_scope": false,
  "unknown_entities": [],
  "language": "fr",
  "summary": "<Résumé en une phrase claire en français de ce que l'utilisateur demande>"
}
```
"""


class RequestInterpreterAgent:
    """Parses user queries into structured positions, weights, and intent."""

    def __init__(self, bedrock_client: BedrockConverseClient | None = None):
        self.bedrock = bedrock_client or BedrockConverseClient()

    def interpret(
        self,
        question: str,
        universe_df: pd.DataFrame | None = None,
        registry: EvidenceRegistry | None = None,
        trace: ExecutionTrace | None = None,
    ) -> ParsedRequest:
        """Interpret natural language request using Claude Haiku with deterministic fallback."""
        if not question or not question.strip():
            empty = ParsedRequest(
                intent="general_allocation",
                summary="Allocation générale optimisée selon le profil de référence.",
            )
            return empty

        if trace:
            trace.step_start("0. Interprétation du Langage Naturel", f"Analyse sémantique de la demande : '{question[:60]}...'")

        parsed: ParsedRequest | None = None

        # 1. Attempt Bedrock Haiku Interpretation
        try:
            messages = [{"role": "user", "content": [{"text": f"Question de l'investisseur : \"{question}\""}]}]
            response = self.bedrock.converse(
                messages=messages,
                system_prompt=INTERPRETER_SYSTEM_PROMPT,
                model_id=MODEL_HAIKU,
                max_tokens=800,
            )
            raw_text = self.bedrock.extract_text(response)
            parsed = self._parse_json_response(raw_text)
        except Exception as e:
            logger.warning(f"Bedrock Haiku interpretation fallback triggered: {e}")

        # 2. Fallback to Deterministic Heuristic Parser if Bedrock failed or returned None
        if parsed is None:
            parsed = self._deterministic_fallback_parse(question, universe_df)

        # 3. Register as Institutional Evidence
        if registry is not None:
            e_item = registry.register(
                tool="request_interpreter",
                args={"question": question},
                result=parsed.model_dump(),
                source="Agent Interpréteur AlphaForge (Claude Haiku 3.5 & Cartographie de l'Univers)",
                date_str="2026-11-13",
                currency="CAD",
                description="Interprétation sémantique et structurée de la demande investisseur.",
            )
            if trace:
                trace.evidence_added(
                    evidence_id=e_item.id,
                    tool=e_item.tool,
                    summary=f"Intention : {parsed.intent} | Actifs demandés : {[p.ticker for p in parsed.requested_positions]}",
                )

        return parsed

    @staticmethod
    def _parse_json_response(raw_text: str) -> ParsedRequest | None:
        """Extract and validate JSON from model output."""
        cleaned = raw_text.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()
            else:
                cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(cleaned)
            return ParsedRequest.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to validate ParsedRequest JSON: {e}")
            return None

    @staticmethod
    def _deterministic_fallback_parse(question: str, universe_df: pd.DataFrame | None = None) -> ParsedRequest:
        """Deterministic regex-based fallback extractor for colloquial company names and weights."""
        q_lower = question.lower()
        requested_positions: list[RequestedPosition] = []
        unknown_entities: list[str] = []
        out_of_scope = False

        # Extract percentage if present
        pct_match = PERCENT_PATTERN.search(q_lower)
        extracted_weight = None
        if pct_match:
            val_str = pct_match.group(1).replace(",", ".")
            try:
                extracted_weight = round(float(val_str) / 100.0, 4)
            except ValueError:
                pass
        elif "moitié" in q_lower:
            extracted_weight = 0.50
        elif "tout" in q_lower or "100%" in q_lower or "totalité" in q_lower:
            extracted_weight = 1.00

        # Scan for known company names
        found_tickers: set[str] = set()
        for alias, ticker in COMPANY_TICKER_MAP.items():
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, q_lower):
                if ticker not in found_tickers:
                    found_tickers.add(ticker)
                    requested_positions.append(
                        RequestedPosition(
                            ticker=ticker,
                            weight=extracted_weight,
                            company_name=alias.title(),
                        )
                    )

        # Out-of-scope triggers
        if any(term in q_lower for term in ["option", "levier", "leverage", "future", "penny", "garanti", "rendement certain"]):
            out_of_scope = True

        intent = "general_allocation"
        if requested_positions:
            intent = "add_position"
        elif "esg" in q_lower or "durable" in q_lower or "vert" in q_lower or "carbone" in q_lower:
            intent = "screen_esg"
        elif "risque" in q_lower or "volatilité" in q_lower or "perte" in q_lower:
            intent = "risk_query"
        elif out_of_scope:
            intent = "out_of_scope"

        summary = f"Demande analysée : {intent}"
        if requested_positions:
            pos_strs = [f"{p.company_name} ({p.ticker})" + (f" à {p.weight:.0%}" if p.weight else "") for p in requested_positions]
            summary = f"Demande d'intégration d'actifs : {', '.join(pos_strs)}."

        return ParsedRequest(
            intent=intent,
            requested_positions=requested_positions,
            out_of_scope=out_of_scope,
            unknown_entities=unknown_entities,
            language="fr",
            summary=summary,
        )
