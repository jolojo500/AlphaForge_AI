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
   - Bitcoin -> BTC-USD, Ethereum/Ether -> ETH-USD
   - Cryptomonnaies (général) -> BTC-USD et ETH-USD
   - Enbridge -> ENB.TO
   - Apple -> AAPL, Microsoft -> MSFT, NVIDIA -> NVDA, Amazon -> AMZN, Alphabet/Google -> GOOGL
   - Canadian Natural Resources -> CNQ.TO, Fortis -> FTS.TO, Royal Bank -> RY.TO, TD -> TD.TO
   - FNB : SPY (S&P 500), QQQ (Nasdaq), XIU.TO (TSX 60), ESGV (ESG), XBB.TO / AGG / ZST.TO (Obligations), GLD (Or).
2. EXTRACTION DU POIDS & RÉPARTITION :
   - Si l'utilisateur mentionne un pourcentage total pour plusieurs actifs (ex: "100% en crypto", "mets tout en Bitcoin et Ethereum"), indique total_requested_weight: 1.00 et répartis équitablement (50/50 -> weight: 0.50 chacun) en marquant is_hypothesized: true et hypothesis_note: "Répartition équipondérée 50/50 de l'enveloppe de 100%".
   - Si un actif a un pourcentage explicite (ex: "20% dans Tesla"), indique weight: 0.20, is_hypothesized: false.
   - Si AUCUN pourcentage n'est précisé (ex: "ajouter Enbridge pour son dividende"), laisse weight: null, is_hypothesized: false, hypothesis_note: "Pondération non précisée".
   - Ne JAMAIS inventer silencieusement un poids par défaut (ex. 0.20).
3. ACTIFS HORS UNIVERS : Si l'utilisateur demande une action non répertoriée (ex: GameStop, Dogecoin, micro-caps), place-la dans 'unknown_entities' et mets 'out_of_scope: true'. Ne JAMAIS inventer un ticker.
4. HORS MANDAT : Mets 'out_of_scope: true' si la demande concerne des options, du levier, des conseils fiscaux, ou une exécution réelle d'ordres.
5. FORMAT DE SORTIE : Réponds STRICTEMENT en format JSON valide conforme au schéma :

```json
{
  "intent": "add_position" | "screen_esg" | "risk_query" | "general_allocation" | "out_of_scope",
  "total_requested_weight": 1.00 | null,
  "requested_positions": [
    {
      "ticker": "TSLA",
      "weight": 0.20,
      "company_name": "Tesla",
      "is_hypothesized": false,
      "hypothesis_note": ""
    }
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
        else:
            # Post-process Haiku response: handle total_requested_weight splitting if positions have null weights
            parsed = self._post_process_parsed_request(parsed, question)

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
        """Parse Bedrock Haiku JSON output into ParsedRequest model."""
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
            logger.warning(f"Failed to parse Haiku JSON response: {e}")
            return None

    @staticmethod
    def _post_process_parsed_request(parsed: ParsedRequest, question: str) -> ParsedRequest:
        """Ensure total weight envelopes are split equally as marked hypotheses without silent defaults."""
        q_lower = question.lower()
        total_w = parsed.total_requested_weight
        if total_w is None:
            if "100%" in q_lower or "tout" in q_lower or "totalité" in q_lower:
                total_w = 1.00
                parsed.total_requested_weight = 1.00

        # If multiple positions exist and weights are missing or total needs splitting
        if parsed.requested_positions and total_w is not None:
            missing_weights = [p for p in parsed.requested_positions if p.weight is None]
            if len(missing_weights) == len(parsed.requested_positions) and len(parsed.requested_positions) > 1:
                split_w = round(total_w / len(parsed.requested_positions), 4)
                for p in parsed.requested_positions:
                    p.weight = split_w
                    p.is_hypothesized = True
                    p.hypothesis_note = f"Hypothèse de répartition équipondérée ({split_w:.1%}) de l'enveloppe totale de {total_w:.0%}"
            elif len(parsed.requested_positions) == 1 and parsed.requested_positions[0].weight is None:
                parsed.requested_positions[0].weight = total_w
                parsed.requested_positions[0].is_hypothesized = False

        return parsed

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
        raw_positions: list[dict[str, Any]] = []
        for alias, ticker in COMPANY_TICKER_MAP.items():
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, q_lower):
                if ticker not in found_tickers:
                    found_tickers.add(ticker)
                    raw_positions.append({"ticker": ticker, "company_name": alias.title()})

        # If general crypto is requested, include both BTC and ETH in universe representation
        if any(term in q_lower for term in ["crypto", "cryptomonnaie", "cryptomonnaies"]):
            if "BTC-USD" not in found_tickers:
                found_tickers.add("BTC-USD")
                raw_positions.append({"ticker": "BTC-USD", "company_name": "Bitcoin"})
            if "ETH-USD" not in found_tickers:
                found_tickers.add("ETH-USD")
                raw_positions.append({"ticker": "ETH-USD", "company_name": "Ethereum"})

        # Distribute extracted total weight across found positions (Issue #33)
        if raw_positions:
            if extracted_weight is not None and len(raw_positions) > 1:
                split_w = round(extracted_weight / len(raw_positions), 4)
                for rp in raw_positions:
                    requested_positions.append(
                        RequestedPosition(
                            ticker=rp["ticker"],
                            weight=split_w,
                            company_name=rp["company_name"],
                            is_hypothesized=True,
                            hypothesis_note=f"Hypothèse de répartition équipondérée ({split_w:.1%}) de l'enveloppe totale de {extracted_weight:.0%}",
                        )
                    )
            elif extracted_weight is not None and len(raw_positions) == 1:
                rp = raw_positions[0]
                requested_positions.append(
                    RequestedPosition(
                        ticker=rp["ticker"],
                        weight=extracted_weight,
                        company_name=rp["company_name"],
                        is_hypothesized=False,
                        hypothesis_note="",
                    )
                )
            else:
                for rp in raw_positions:
                    requested_positions.append(
                        RequestedPosition(
                            ticker=rp["ticker"],
                            weight=None,
                            company_name=rp["company_name"],
                            is_hypothesized=False,
                            hypothesis_note="Pondération non précisée dans la requête",
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
            pos_strs = [f"{p.company_name} ({p.ticker})" + (f" à {p.weight:.1%}" if p.weight else " (poids non précisé)") for p in requested_positions]
            summary = f"Demande d'intégration d'actifs : {', '.join(pos_strs)}."

        return ParsedRequest(
            intent=intent,
            total_requested_weight=extracted_weight,
            requested_positions=requested_positions,
            out_of_scope=out_of_scope,
            unknown_entities=unknown_entities,
            language="fr",
            summary=summary,
        )
