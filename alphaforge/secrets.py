"""Secrets and API keys management via Environment Variables and AWS SSM Parameter Store.

Keys are NEVER committed to source control or container images (PRD §8, B-9).
Order of precedence:
1. Environment variable (e.g. FINNHUB_API_KEY, TAVILY_API_KEY)
2. AWS Systems Manager (SSM) Parameter Store (e.g. /alphaforge/finnhub_api_key)
3. None (graceful fallback to cache with diagnostic warning)
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

SSM_MAPPINGS: dict[str, str] = {
    "FINNHUB_API_KEY": "/alphaforge/finnhub_api_key",
    "TAVILY_API_KEY": "/alphaforge/tavily_api_key",
    "AF_ADVISOR_PASSWORD": "/alphaforge/advisor_password",
}


@lru_cache(maxsize=16)
def get_ssm_parameter(param_name: str, region_name: str | None = None) -> str | None:
    """Fetch secret string from AWS SSM Parameter Store with decryption.

    Results are cached in memory for the life of the process.
    Returns None if AWS credentials are not configured, parameter does not exist,
    or on any client error.
    """
    region = region_name or os.getenv("AWS_REGION", "us-east-1")
    try:
        import boto3

        ssm = boto3.client("ssm", region_name=region)
        resp = ssm.get_parameter(Name=param_name, WithDecryption=True)
        val = resp.get("Parameter", {}).get("Value")
        if val:
            logger.info("Successfully loaded secret parameter %s from SSM", param_name)
            return val
    except Exception as exc:
        logger.debug("Could not fetch SSM parameter %s: %s", param_name, exc)
    return None


def get_secret(env_name: str, ssm_param_name: str | None = None) -> str | None:
    """Get secret value from env var, falling back to SSM Parameter Store.

    If found in SSM, sets os.environ[env_name] so child calls or libraries can read it directly.
    """
    val = os.getenv(env_name)
    if val:
        return val

    param = ssm_param_name or SSM_MAPPINGS.get(env_name)
    if param:
        ssm_val = get_ssm_parameter(param)
        if ssm_val:
            os.environ[env_name] = ssm_val
            return ssm_val

    return None
