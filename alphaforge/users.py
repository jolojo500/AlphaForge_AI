"""User profile and account persistence with Local and DynamoDB backends (PRD C-14, #128)."""

from __future__ import annotations

import abc
import datetime as dt
import json
import logging
import os
from decimal import Decimal
from typing import Any

import boto3

from alphaforge.data.market_db import get_user_profile_db, save_user_profile_db
from alphaforge.personas import PERSONAS

logger = logging.getLogger(__name__)


def _to_dynamodb_friendly(obj: Any) -> Any:
    """Recursively convert float to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamodb_friendly(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamodb_friendly(v) for v in obj]
    return obj


def _from_dynamodb_friendly(obj: Any) -> Any:
    """Recursively convert Decimal to float/int for JSON/API compatibility."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _from_dynamodb_friendly(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_dynamodb_friendly(v) for v in obj]
    return obj


class UserStore(abc.ABC):
    @abc.abstractmethod
    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve user profile and metadata by user_id or username."""
        pass

    @abc.abstractmethod
    def save_user_profile(
        self,
        user_id: str,
        profile: dict[str, Any],
        current_holdings: Any = None,
        account_type: str | None = None,
        username: str | None = None,
        email: str | None = None,
        is_advisor: bool = False,
    ) -> dict[str, Any]:
        """Save or update user profile and metadata."""
        pass


class LocalUserStore(UserStore):
    """In-memory user store for testing and offline development."""

    def __init__(self) -> None:
        self._users: dict[str, dict[str, Any]] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        now = dt.datetime.now(dt.UTC).isoformat()
        defaults = {
            "amira": {
                "user_id": "amira",
                "username": "amira",
                "email": "amira@alphaforge.demo",
                "profile": dict(PERSONAS.get("amira", {})),
                "account_type": "CELI",
                "current_holdings": None,
                "is_advisor": False,
                "updated_at": now,
            },
            "mateo": {
                "user_id": "mateo",
                "username": "mateo",
                "email": "mateo@alphaforge.demo",
                "profile": dict(PERSONAS.get("mateo", {})),
                "account_type": "REER",
                "current_holdings": None,
                "is_advisor": False,
                "updated_at": now,
            },
            "robert": {
                "user_id": "robert",
                "username": "robert",
                "email": "robert@alphaforge.demo",
                "profile": dict(PERSONAS.get("robert", {})),
                "account_type": "Non enregistré",
                "current_holdings": None,
                "is_advisor": False,
                "updated_at": now,
            },
            "advisor": {
                "user_id": "advisor",
                "username": "advisor",
                "email": "advisor@alphaforge.demo",
                "profile": {},
                "account_type": None,
                "current_holdings": None,
                "is_advisor": True,
                "updated_at": now,
            },
        }
        self._users.update(defaults)

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        user = self._users.get(user_id)
        if user:
            return json.loads(json.dumps(user))
        # Fallback check by username
        for u in self._users.values():
            if u.get("username") == user_id:
                return json.loads(json.dumps(u))
        # SQLite DB fallback
        db_user = get_user_profile_db(user_id)
        if db_user:
            self._users[user_id] = db_user
            return db_user
        # If demo persona
        if user_id in PERSONAS:
            return {
                "user_id": user_id,
                "username": user_id,
                "email": f"{user_id}@alphaforge.demo",
                "profile": dict(PERSONAS[user_id]),
                "account_type": None,
                "current_holdings": None,
                "is_advisor": False,
                "updated_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        return None

    def save_user_profile(
        self,
        user_id: str,
        profile: dict[str, Any],
        current_holdings: Any = None,
        account_type: str | None = None,
        username: str | None = None,
        email: str | None = None,
        is_advisor: bool = False,
    ) -> dict[str, Any]:
        existing = self.get_user_profile(user_id) or {}
        now = dt.datetime.now(dt.UTC).isoformat()
        item = {
            "user_id": user_id,
            "username": username or existing.get("username") or user_id,
            "email": email or existing.get("email") or f"{user_id}@alphaforge.demo",
            "profile": profile,
            "current_holdings": current_holdings if current_holdings is not None else existing.get("current_holdings"),
            "account_type": account_type if account_type is not None else existing.get("account_type"),
            "is_advisor": is_advisor or existing.get("is_advisor", False),
            "updated_at": now,
        }
        self._users[user_id] = item
        if username and username != user_id:
            self._users[username] = item
        save_user_profile_db(
            user_id=user_id,
            profile=profile,
            current_holdings=item["current_holdings"],
            account_type=item["account_type"],
            username=item["username"],
            email=item["email"],
            is_advisor=item["is_advisor"],
            updated_at=now,
        )
        return json.loads(json.dumps(item))


class DynamoDBUserStore(UserStore):
    """DynamoDB user store."""

    def __init__(
        self,
        table_name: str | None = None,
        region_name: str | None = None,
        table_resource: Any = None,
    ) -> None:
        self.table_name = table_name or os.getenv("AF_USERS_TABLE", "alphaforge-users")
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")

        if table_resource is not None:
            self._table = table_resource
        else:
            profile = os.getenv("AWS_PROFILE")
            if profile:
                session = boto3.Session(profile_name=profile, region_name=self.region_name)
            else:
                session = boto3.Session(region_name=self.region_name)
            dynamodb = session.resource("dynamodb", region_name=self.region_name)
            self._table = dynamodb.Table(self.table_name)

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        try:
            resp = self._table.get_item(Key={"user_id": user_id})
            item = resp.get("Item")
            if item:
                return _from_dynamodb_friendly(item)
        except Exception:
            logger.exception("Failed to get user %s from DynamoDB table %s", user_id, self.table_name)

        # Fallback to SQLite DB
        db_user = get_user_profile_db(user_id)
        if db_user:
            return db_user

        # Fallback to PERSONAS if matching demo account
        if user_id in PERSONAS:
            return {
                "user_id": user_id,
                "username": user_id,
                "email": f"{user_id}@alphaforge.demo",
                "profile": dict(PERSONAS[user_id]),
                "account_type": None,
                "current_holdings": None,
                "is_advisor": False,
                "updated_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        return None

    def save_user_profile(
        self,
        user_id: str,
        profile: dict[str, Any],
        current_holdings: Any = None,
        account_type: str | None = None,
        username: str | None = None,
        email: str | None = None,
        is_advisor: bool = False,
    ) -> dict[str, Any]:
        existing = self.get_user_profile(user_id) or {}
        now = dt.datetime.now(dt.UTC).isoformat()
        item = {
            "user_id": user_id,
            "username": username or existing.get("username") or user_id,
            "email": email or existing.get("email") or f"{user_id}@alphaforge.demo",
            "profile": profile,
            "current_holdings": current_holdings if current_holdings is not None else existing.get("current_holdings"),
            "account_type": account_type if account_type is not None else existing.get("account_type"),
            "is_advisor": is_advisor or existing.get("is_advisor", False),
            "updated_at": now,
        }
        db_item = _to_dynamodb_friendly(item)
        try:
            self._table.put_item(Item=db_item)
            if username and username != user_id:
                alt_item = dict(db_item, user_id=username)
                self._table.put_item(Item=alt_item)
        except Exception:
            logger.exception("Failed to save user %s to DynamoDB table %s", user_id, self.table_name)
            raise
        finally:
            save_user_profile_db(
                user_id=user_id,
                profile=profile,
                current_holdings=item["current_holdings"],
                account_type=item["account_type"],
                username=item["username"],
                email=item["email"],
                is_advisor=item["is_advisor"],
                updated_at=now,
            )
        return item


_global_user_store: UserStore | None = None


def get_user_store() -> UserStore:
    global _global_user_store
    if _global_user_store is not None:
        return _global_user_store

    backend = os.getenv("AF_USERS_BACKEND")
    if not backend:
        # If running in pytest or no AWS credentials, default to local
        if "PYTEST_CURRENT_TEST" in os.environ or os.getenv("AF_AUTH") == "off":
            backend = "local"
        else:
            backend = "dynamodb"

    if backend == "dynamodb":
        try:
            _global_user_store = DynamoDBUserStore()
        except Exception:
            logger.warning("Falling back to LocalUserStore because DynamoDBUserStore initialization failed")
            _global_user_store = LocalUserStore()
    else:
        _global_user_store = LocalUserStore()

    return _global_user_store


def set_user_store_override(store: UserStore | None) -> None:
    """Override user store for tests."""
    global _global_user_store
    _global_user_store = store
