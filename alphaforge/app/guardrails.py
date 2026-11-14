"""Amazon Bedrock Guardrails integration for AlphaForge AI.

Complies with institutional governance requirements:
- Loads guardrail metadata from config/guardrail.json (no secrets stored).
- Provides helper guardrail_config() returning the Converse guardrailConfig dict
  (or None if config missing).
- Provides apply_guardrail(text, source) using bedrock-runtime ApplyGuardrail
  for evaluating inputs/outputs prior to agent orchestration.
- Pure evaluation function: returns {blocked, action, message, assessments_summary}
  and registers nothing itself (caller logs evidence and trace).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Default config location at repo root: config/guardrail.json
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "guardrail.json"


def load_guardrail_config(config_path: str | Path | None = None) -> dict[str, Any] | None:
    """Load Bedrock Guardrail configuration from JSON.

    Looks in config_path, then ALPHAFORGE_GUARDRAIL_CONFIG env var, then DEFAULT_CONFIG_PATH.
    Returns normalized dict or None if missing/invalid.
    """
    target_path = (
        Path(config_path)
        if config_path
        else Path(os.environ.get("ALPHAFORGE_GUARDRAIL_CONFIG", DEFAULT_CONFIG_PATH))
    )

    if not target_path.exists():
        logger.debug(f"Guardrail config file not found at {target_path}")
        return None

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        guardrail_id = data.get("guardrail_id") or data.get("guardrailIdentifier")
        guardrail_version = str(data.get("guardrail_version") or data.get("guardrailVersion") or "1")

        if not guardrail_id:
            logger.warning(f"Guardrail config at {target_path} missing 'guardrail_id'")
            return None

        return {
            "guardrail_id": guardrail_id,
            "guardrail_version": guardrail_version,
            "guardrail_arn": data.get("guardrail_arn"),
            "name": data.get("name", "alphaforge-guardrail"),
            "region": data.get("region", "us-east-1"),
            "denied_topics": data.get("denied_topics", []),
            "content_filters": data.get("content_filters", []),
            "pii_entities": data.get("pii_entities", []),
        }
    except Exception as exc:
        logger.warning(f"Failed to read guardrail config from {target_path}: {exc}")
        return None


def guardrail_config(
    config: dict[str, Any] | None = None,
    trace: str = "enabled",
    config_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return the guardrailConfig dict required by the Bedrock Converse API.

    Returns None if the configuration file is missing or invalid.
    """
    cfg = config or load_guardrail_config(config_path)
    if not cfg or not cfg.get("guardrail_id"):
        return None

    return {
        "guardrailIdentifier": cfg["guardrail_id"],
        "guardrailVersion": str(cfg["guardrail_version"]),
        "trace": trace,
    }


def get_bedrock_runtime_client(
    profile_name: str | None = None,
    region_name: str = "us-east-1",
) -> Any:
    """Initialize Bedrock Runtime client."""
    profile = profile_name or os.environ.get("AWS_PROFILE", "datathon")
    config = Config(
        retries={"mode": "adaptive", "max_attempts": 3},
        read_timeout=60,
        connect_timeout=15,
    )
    try:
        session = boto3.Session(profile_name=profile, region_name=region_name)
        return session.client("bedrock-runtime", config=config)
    except Exception as exc:
        logger.warning(f"Failed to initialize profile '{profile}', falling back to default session: {exc}")
        session = boto3.Session(region_name=region_name)
        return session.client("bedrock-runtime", config=config)


def apply_guardrail(
    text: str,
    source: str = "INPUT",
    client: Any = None,
    config_dict: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate text against Amazon Bedrock Guardrail.

    Args:
        text: Input prompt or model output to evaluate.
        source: 'INPUT' (for user questions) or 'OUTPUT' (for model responses).
        client: Optional pre-configured bedrock-runtime client.
        config_dict: Optional override of guardrail configuration dict.
        config_path: Optional path to guardrail.json config file.

    Returns:
        dict: {
            "blocked": bool,
            "action": str ("NONE" | "GUARDRAIL_INTERVENED"),
            "message": str (intervening messaging or empty),
            "assessments_summary": list[dict],
        }
    """
    cfg = config_dict or load_guardrail_config(config_path)
    if not cfg or not cfg.get("guardrail_id"):
        logger.debug("Guardrail config not found. Bypassing guardrail evaluation.")
        return {
            "blocked": False,
            "action": "NONE",
            "message": "",
            "assessments_summary": [],
            "reason": "guardrail_config_missing",
        }

    guardrail_id = cfg["guardrail_id"]
    guardrail_version = str(cfg.get("guardrail_version", "1"))
    region = cfg.get("region", "us-east-1")

    rt_client = client or get_bedrock_runtime_client(region_name=region)

    try:
        response = rt_client.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=guardrail_version,
            source=source,
            content=[{"text": {"text": text}}],
        )
    except ClientError as exc:
        logger.error(f"Bedrock ApplyGuardrail ClientError: {exc}")
        raise
    except Exception as exc:
        logger.error(f"Unexpected error in ApplyGuardrail: {exc}")
        raise

    action = response.get("action", "NONE")
    blocked = (action == "GUARDRAIL_INTERVENED")

    outputs = response.get("outputs", [])
    message = outputs[0].get("text", "") if outputs else ""

    assessments_summary: list[dict[str, Any]] = []
    for assessment in response.get("assessments", []):
        if not isinstance(assessment, dict):
            continue

        # Topic Policy evaluations
        if "topicPolicy" in assessment:
            for topic in assessment["topicPolicy"].get("topics", []):
                if topic.get("action") == "BLOCKED" or topic.get("detected"):
                    assessments_summary.append({
                        "policy": "topic",
                        "name": topic.get("name"),
                        "action": topic.get("action", "BLOCKED"),
                        "type": topic.get("type", "DENY"),
                    })

        # Content Policy evaluations
        if "contentPolicy" in assessment:
            for cfilter in assessment["contentPolicy"].get("filters", []):
                if cfilter.get("action") == "BLOCKED" or cfilter.get("confidence") in ("MEDIUM", "HIGH"):
                    assessments_summary.append({
                        "policy": "content",
                        "type": cfilter.get("type"),
                        "action": cfilter.get("action", "BLOCKED"),
                        "confidence": cfilter.get("confidence"),
                    })

        # Sensitive Information Policy (PII) evaluations
        if "sensitiveInformationPolicy" in assessment:
            for pii in assessment["sensitiveInformationPolicy"].get("piiEntities", []):
                assessments_summary.append({
                    "policy": "pii",
                    "type": pii.get("type"),
                    "action": pii.get("action", "ANONYMIZE"),
                    "match": pii.get("match"),
                })
            for regex in assessment["sensitiveInformationPolicy"].get("regexes", []):
                assessments_summary.append({
                    "policy": "regex",
                    "name": regex.get("name"),
                    "action": regex.get("action", "ANONYMIZE"),
                })

    return {
        "blocked": blocked,
        "action": action,
        "message": message,
        "assessments_summary": assessments_summary,
    }
