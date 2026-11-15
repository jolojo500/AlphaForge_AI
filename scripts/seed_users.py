"""Seed demo user accounts in DynamoDB alphaforge-users table (PRD C-14, #128)."""

from __future__ import annotations

import datetime as dt
import logging
import os
from decimal import Decimal

import boto3

from alphaforge.personas import PERSONAS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _to_dynamodb_friendly(obj: object) -> object:
    """Recursively convert float to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamodb_friendly(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamodb_friendly(v) for v in obj]
    return obj


COGNITO_SUBS = {
    "amira": "24185498-b001-7011-36cc-2fb461a17fe1",
    "mateo": "1428a4b8-20a1-7002-c0ff-f9c27cc34d23",
    "robert": "945864c8-5041-704e-8390-ad1961488d00",
    "advisor": "0428f488-70d1-70dc-c769-4ccfafb41d23",
}

ACCOUNT_TYPES = {
    "amira": "CELI",
    "mateo": "REER",
    "robert": "Non enregistré",
    "advisor": None,
}


def seed_users(table_name: str = "alphaforge-users", region_name: str = "us-east-1") -> None:
    profile = os.getenv("AWS_PROFILE", "datathon")
    session = boto3.Session(profile_name=profile, region_name=region_name)
    dynamodb = session.resource("dynamodb", region_name=region_name)
    table = dynamodb.Table(table_name)

    now = dt.datetime.now(dt.UTC).isoformat()

    for username, persona in PERSONAS.items():
        sub = COGNITO_SUBS.get(username)
        account_type = ACCOUNT_TYPES.get(username)

        # Base item data
        item_data = {
            "username": username,
            "email": f"{username}@alphaforge.demo",
            "profile": _to_dynamodb_friendly(persona),
            "account_type": account_type,
            "current_holdings": None,
            "is_advisor": False,
            "updated_at": now,
        }

        # Save with user_id = username
        by_username = dict(item_data, user_id=username)
        table.put_item(Item=by_username)
        logging.info("Seeded user '%s' in %s", username, table_name)

        # Also save with user_id = sub
        if sub:
            by_sub = dict(item_data, user_id=sub)
            table.put_item(Item=by_sub)
            logging.info("Seeded sub '%s' (%s) in %s", sub, username, table_name)

    # Seed advisor account
    advisor_sub = COGNITO_SUBS.get("advisor")
    advisor_data = {
        "username": "advisor",
        "email": "advisor@alphaforge.demo",
        "profile": {},
        "account_type": None,
        "current_holdings": None,
        "is_advisor": True,
        "updated_at": now,
    }
    table.put_item(Item=dict(advisor_data, user_id="advisor"))
    logging.info("Seeded user 'advisor' in %s", table_name)
    if advisor_sub:
        table.put_item(Item=dict(advisor_data, user_id=advisor_sub))
        logging.info("Seeded sub '%s' (advisor) in %s", advisor_sub, table_name)


def sync_cognito_passwords(
    user_pool_id: str | None = None,
    region_name: str = "us-east-1",
) -> None:
    """Set Cognito passwords for demo accounts; advisor password is read from AF_ADVISOR_PASSWORD."""
    pool_id = user_pool_id or os.getenv("AF_COGNITO_USER_POOL_ID", "us-east-1_XjxuVar8b")
    profile = os.getenv("AWS_PROFILE", "datathon")
    session = boto3.Session(profile_name=profile, region_name=region_name)
    client = session.client("cognito-idp", region_name=region_name)

    demo_password = os.getenv("AF_DEMO_CLIENT_PASSWORD", "AlphaForge2026!")
    for user in ("amira", "mateo", "robert"):
        try:
            client.admin_set_user_password(
                UserPoolId=pool_id,
                Username=user,
                Password=demo_password,
                Permanent=True,
            )
            logging.info("Set Cognito demo password for '%s'", user)
        except Exception as exc:
            logging.warning("Could not set password for %s: %s", user, exc)

    advisor_password = os.getenv("AF_ADVISOR_PASSWORD")
    if advisor_password:
        try:
            client.admin_set_user_password(
                UserPoolId=pool_id,
                Username="advisor",
                Password=advisor_password,
                Permanent=True,
            )
            logging.info("Set Cognito password for 'advisor' from AF_ADVISOR_PASSWORD")
        except Exception as exc:
            logging.warning("Could not set password for advisor: %s", exc)
    else:
        logging.info("AF_ADVISOR_PASSWORD not set; advisor password left unchanged.")


if __name__ == "__main__":
    import sys

    table = os.getenv("AF_USERS_TABLE", "alphaforge-users")
    region = os.getenv("AWS_REGION", "us-east-1")
    seed_users(table, region)

    if "--sync-cognito" in sys.argv:
        sync_cognito_passwords(region_name=region)
