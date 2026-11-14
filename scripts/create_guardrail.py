#!/usr/bin/env python3
"""Create or update the Amazon Bedrock Guardrail for AlphaForge AI.

Idempotent deployment script:
1. Connects to AWS Bedrock in us-east-1 using AWS_PROFILE (default 'datathon').
2. Checks whether 'alphaforge-guardrail' already exists:
   - If exists, updates draft configuration.
   - If not, creates new guardrail.
3. Sets up:
   - Denied Topics:
     * personalized-financial-advice (personal advice to real persons)
     * executing-real-trades (placing/routing real orders)
     * guaranteed-return-promises (promises/guarantees of future returns)
   - Content Filters: moderate filters on harmful content categories.
   - Sensitive Information Policy (PII): anonymization of emails, phone numbers,
     bank account numbers, credit/debit cards, and SIN.
   - Bilingual French + English blocked messaging.
4. Waits for DRAFT status to reach 'READY', then creates a new published version.
5. Waits for published version status to reach 'READY'.
6. Writes guardrail identifier, version, and ARN to config/guardrail.json (no secrets).
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("create_guardrail")

GUARDRAIL_NAME = "alphaforge-guardrail"
GUARDRAIL_DESCRIPTION = (
    "AlphaForge Bedrock Guardrail: blocks personalized financial advice, "
    "real trade execution, and guaranteed returns; filters content and anonymizes PII."
)

BLOCKED_MESSAGE = (
    "AlphaForge est un outil de simulation éducative et d'aide à la décision. "
    "Nous ne fournissons aucun conseil financier personnalisé, n'exécutons aucune transaction réelle "
    "et ne garantissons aucun rendement futur. / AlphaForge is an educational simulation tool. "
    "We do not provide personalized financial advice, execute real transactions, or guarantee returns."
)

TOPIC_POLICY_CONFIG: dict[str, Any] = {
    "topicsConfig": [
        {
            "name": "personalized-financial-advice",
            "definition": (
                "Fiduciary investment advice using real personal identity, real bank accounts, or confidential "
                "tax data. Excludes hypothetical simulations, portfolio scenarios, and opinions on stock/ETF/crypto risk."
            ),
            "examples": [
                "Mon courriel est jean.tremblay@gmail.com, conseille-moi personnellement",
                "Voici mon NAS 123-456-789, gère mon patrimoine et mes impôts réels",
                "Donne un conseil financier personnel pour mon compte bancaire réel",
                "Mon compte bancaire est le 987654, quel titre dois-je acheter ?",
                "Provide personal fiduciary advice for my real registered tax account",
            ],
            "type": "DENY",
        },
        {
            "name": "executing-real-trades",
            "definition": (
                "Executing, placing, routing, or processing real buy or sell orders, interacting "
                "directly with real brokerage accounts, or conducting financial transactions."
            ),
            "examples": [
                "Achète 1000 actions TSLA dans mon compte maintenant",
                "Passe un ordre de vente sur mon compte BNCD 12345678",
                "Execute a real order to sell 50 shares of Apple",
                "Buy 10 shares of NVDA right now on my live account",
                "Vends toutes les positions de mon compte de courtage",
            ],
            "type": "DENY",
        },
        {
            "name": "guaranteed-return-promises",
            "definition": (
                "Promising or guaranteeing specific future investment returns, certainty of financial gains, "
                "or risk-free profits. Excludes educational questions on historical return or asset yield."
            ),
            "examples": [
                "Garantis-moi 15% de rendement par an",
                "Peux-tu me garantir 15% de rendement sans aucun risque ?",
                "Can you guarantee that I will double my money within one year?",
                "Promets-moi que ce placement ne perdra jamais d argent",
                "Assure-moi un profit certain sur cet investissement",
            ],
            "type": "DENY",
        },
    ]
}

CONTENT_POLICY_CONFIG: dict[str, Any] = {
    "filtersConfig": [
        {"type": "SEXUAL", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
        {"type": "VIOLENCE", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
        {"type": "HATE", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
        {"type": "INSULTS", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
        {"type": "MISCONDUCT", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
        {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"},
    ]
}

SENSITIVE_INFO_POLICY_CONFIG: dict[str, Any] = {
    "piiEntitiesConfig": [
        {"type": "EMAIL", "action": "ANONYMIZE"},
        {"type": "PHONE", "action": "ANONYMIZE"},
        {"type": "US_BANK_ACCOUNT_NUMBER", "action": "ANONYMIZE"},
        {"type": "INTERNATIONAL_BANK_ACCOUNT_NUMBER", "action": "ANONYMIZE"},
        {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "ANONYMIZE"},
        {"type": "CA_SOCIAL_INSURANCE_NUMBER", "action": "ANONYMIZE"},
    ]
}


def get_bedrock_client(profile_name: str | None = None, region_name: str = "us-east-1") -> Any:
    """Initialize boto3 Bedrock control-plane client."""
    profile = profile_name or os.environ.get("AWS_PROFILE", "datathon")
    config = Config(
        retries={"mode": "adaptive", "max_attempts": 3},
        read_timeout=60,
        connect_timeout=15,
    )
    try:
        session = boto3.Session(profile_name=profile, region_name=region_name)
        client = session.client("bedrock", config=config)
        logger.info(f"Initialized Bedrock client with profile='{profile}', region='{region_name}'")
        return client
    except Exception as exc:
        logger.warning(f"Could not initialize with profile '{profile}': {exc}. Using default session.")
        session = boto3.Session(region_name=region_name)
        return session.client("bedrock", config=config)


def find_guardrail_by_name(client: Any, name: str) -> dict[str, Any] | None:
    """Find an existing guardrail summary by name, paginating if necessary."""
    next_token = None
    while True:
        kwargs: dict[str, Any] = {"maxResults": 50}
        if next_token:
            kwargs["nextToken"] = next_token
        response = client.list_guardrails(**kwargs)
        for g in response.get("guardrails", []):
            if g.get("name") == name:
                return g
        next_token = response.get("nextToken")
        if not next_token:
            break
    return None


def wait_for_guardrail_status(
    client: Any,
    guardrail_id: str,
    version: str | None = None,
    target_status: str = "READY",
    timeout_sec: int = 60,
    poll_interval: float = 1.5,
) -> dict[str, Any]:
    """Poll Bedrock until the guardrail or guardrail version reaches target_status."""
    start_time = time.time()
    v_desc = f"version {version}" if version else "DRAFT"
    logger.info(f"Waiting for guardrail {guardrail_id} ({v_desc}) to reach status '{target_status}'...")

    while time.time() - start_time < timeout_sec:
        kwargs: dict[str, Any] = {"guardrailIdentifier": guardrail_id}
        if version is not None:
            kwargs["guardrailVersion"] = version
        details = client.get_guardrail(**kwargs)
        current_status = details.get("status")

        if current_status == target_status:
            logger.info(f"Guardrail {guardrail_id} ({v_desc}) reached '{target_status}'.")
            return details
        if current_status == "FAILED":
            failure_reasons = details.get("failureReasons", [])
            raise RuntimeError(f"Guardrail {guardrail_id} ({v_desc}) entered FAILED state: {failure_reasons}")

        time.sleep(poll_interval)

    raise TimeoutError(
        f"Timed out after {timeout_sec}s waiting for guardrail {guardrail_id} ({v_desc}) "
        f"to reach '{target_status}'."
    )


def create_or_update_guardrail(
    client: Any,
    name: str = GUARDRAIL_NAME,
    output_config_path: Path | None = None,
) -> dict[str, Any]:
    """Create or update the Bedrock guardrail, publish a version, and save config."""
    existing = find_guardrail_by_name(client, name)

    if existing is not None:
        guardrail_id = existing["id"]
        logger.info(f"Found existing guardrail '{name}' with id: {guardrail_id}. Updating DRAFT...")
        update_res = client.update_guardrail(
            guardrailIdentifier=guardrail_id,
            name=name,
            description=GUARDRAIL_DESCRIPTION,
            topicPolicyConfig=TOPIC_POLICY_CONFIG,
            contentPolicyConfig=CONTENT_POLICY_CONFIG,
            sensitiveInformationPolicyConfig=SENSITIVE_INFO_POLICY_CONFIG,
            blockedInputMessaging=BLOCKED_MESSAGE,
            blockedOutputsMessaging=BLOCKED_MESSAGE,
        )
        guardrail_arn = update_res.get("guardrailArn") or existing.get("arn")
    else:
        logger.info(f"Guardrail '{name}' does not exist. Creating new guardrail...")
        create_res = client.create_guardrail(
            name=name,
            description=GUARDRAIL_DESCRIPTION,
            topicPolicyConfig=TOPIC_POLICY_CONFIG,
            contentPolicyConfig=CONTENT_POLICY_CONFIG,
            sensitiveInformationPolicyConfig=SENSITIVE_INFO_POLICY_CONFIG,
            blockedInputMessaging=BLOCKED_MESSAGE,
            blockedOutputsMessaging=BLOCKED_MESSAGE,
        )
        guardrail_id = create_res["guardrailId"]
        guardrail_arn = create_res["guardrailArn"]
        logger.info(f"Created guardrail '{name}' with id: {guardrail_id}")

    # Wait for draft to be READY
    wait_for_guardrail_status(client, guardrail_id=guardrail_id, version=None, target_status="READY")

    # Publish a new version
    logger.info(f"Publishing new version for guardrail {guardrail_id}...")
    version_res = client.create_guardrail_version(
        guardrailIdentifier=guardrail_id,
        description=f"AlphaForge AI governance version published at {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
    )
    published_version = version_res["version"]
    logger.info(f"Published version: {published_version}")

    # Wait for published version to be READY
    final_details = wait_for_guardrail_status(
        client,
        guardrail_id=guardrail_id,
        version=published_version,
        target_status="READY",
    )

    result_config = {
        "guardrail_id": guardrail_id,
        "guardrail_arn": final_details.get("guardrailArn") or guardrail_arn,
        "guardrail_version": published_version,
        "name": name,
        "region": client.meta.region_name,
        "status": final_details.get("status", "READY"),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "denied_topics": [t["name"] for t in TOPIC_POLICY_CONFIG["topicsConfig"]],
        "content_filters": [f["type"] for f in CONTENT_POLICY_CONFIG["filtersConfig"]],
        "pii_entities": [p["type"] for p in SENSITIVE_INFO_POLICY_CONFIG["piiEntitiesConfig"]],
    }

    # Save to config/guardrail.json
    if output_config_path is None:
        repo_root = Path(__file__).resolve().parent.parent
        output_config_path = repo_root / "config" / "guardrail.json"

    output_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_config_path, "w", encoding="utf-8") as f:
        json.dump(result_config, f, indent=2)

    logger.info(f"Successfully saved guardrail configuration to: {output_config_path}")
    return result_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update AlphaForge Bedrock Guardrail")
    parser.add_argument("--profile", default=None, help="AWS CLI profile name (default: datathon or AWS_PROFILE)")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("--config-out", default=None, help="Path to write guardrail.json")
    args = parser.parse_args()

    client = get_bedrock_client(profile_name=args.profile, region_name=args.region)
    out_path = Path(args.config_out) if args.config_out else None

    result = create_or_update_guardrail(client, output_config_path=out_path)
    print("\nGuardrail Deployment Summary:")
    print(f"  Guardrail ID:      {result['guardrail_id']}")
    print(f"  Guardrail Version: {result['guardrail_version']}")
    print(f"  Guardrail ARN:     {result['guardrail_arn']}")
    print(f"  Status:            {result['status']}")
    print(f"  Region:            {result['region']}")


if __name__ == "__main__":
    main()
