"""Amazon Cognito authentication, JWT verification, and FastAPI dependencies (PRD C-14, #128)."""

from __future__ import annotations

import datetime as dt
import logging
import os
import threading
from typing import Annotated, Any

import boto3
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

COGNITO_USER_POOL_ID = os.getenv("AF_COGNITO_USER_POOL_ID", "us-east-1_XjxuVar8b")
COGNITO_CLIENT_ID = os.getenv("AF_COGNITO_CLIENT_ID", "9lreq61mqkf01s9h9h48gkcfe")
COGNITO_REGION = os.getenv("AWS_REGION", "us-east-1")
LOCAL_DEV_SECRET = "alphaforge-dev-secret-key-32bytes-long!"

security = HTTPBearer(auto_error=False)


class User(BaseModel):
    user_id: str
    username: str
    email: str | None = None
    groups: list[str] = Field(default_factory=list)

    @property
    def is_advisor(self) -> bool:
        return "advisor" in self.groups


def is_auth_enabled() -> bool:
    """Check if authentication is active (AF_AUTH != 'off')."""
    val = os.getenv("AF_AUTH", "").lower().strip()
    if val == "off":
        return False
    if val == "on":
        return True
    # If explicitly in tests, default to off unless set to on
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    return bool(COGNITO_USER_POOL_ID)


_jwks_client: PyJWKClient | None = None
_jwks_lock = threading.Lock()


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    with _jwks_lock:
        if _jwks_client is None:
            jwks_url = (
                f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
                f"{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
            )
            _jwks_client = PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=10)
        return _jwks_client


def create_dev_token(user: User, expires_in_seconds: int = 3600) -> str:
    """Generate a development JWT signed with local HMAC for offline / dev mode."""
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": user.user_id,
        "cognito:username": user.username,
        "username": user.username,
        "email": user.email,
        "cognito:groups": user.groups,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=expires_in_seconds)).timestamp()),
        "token_use": "id",
    }
    return jwt.encode(payload, LOCAL_DEV_SECRET, algorithm="HS256")


def verify_token(token: str) -> User:
    """Verify Cognito or Dev JWT token and return User object. Raises HTTPException 401 on failure."""
    if not token:
        raise HTTPException(status_code=401, detail="Jeton d'authentification manquant")

    # If auth is off or it's a dev token
    if not is_auth_enabled():
        try:
            payload = jwt.decode(
                token,
                LOCAL_DEV_SECRET,
                algorithms=["HS256"],
                options={"verify_exp": True},
            )
        except Exception:
            try:
                payload = jwt.decode(token, options={"verify_signature": False})
            except Exception as e:
                raise HTTPException(status_code=401, detail=f"Jeton invalide: {e}") from e

        user_id = payload.get("sub") or payload.get("username") or "anonymous"
        username = payload.get("cognito:username") or payload.get("username") or user_id
        email = payload.get("email")
        groups = payload.get("cognito:groups") or []
        if isinstance(groups, str):
            groups = [groups]
        return User(
            user_id=user_id,
            username=username,
            email=email,
            groups=list(groups),
        )

    # When auth is enabled, verify signature via Cognito JWKS
    try:
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg")

        if alg == "HS256":
            payload = jwt.decode(token, LOCAL_DEV_SECRET, algorithms=["HS256"])
        else:
            client = get_jwks_client()
            signing_key = client.get_signing_key_from_jwt(token)
            issuer = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=issuer,
                options={"verify_aud": False},
            )
    except Exception as e:
        logger.warning("Token verification failed: %s", e)
        raise HTTPException(status_code=401, detail=f"Jeton invalide ou expiré: {e}") from e

    user_id = payload.get("sub") or payload.get("username") or "anonymous"
    username = payload.get("cognito:username") or payload.get("username") or user_id
    email = payload.get("email")
    groups = payload.get("cognito:groups") or []
    if isinstance(groups, str):
        groups = [groups]

    return User(
        user_id=user_id,
        username=username,
        email=email,
        groups=list(groups),
    )


def authenticate_user(username: str, password: str) -> dict[str, Any]:
    """Authenticate username & password against Cognito (or offline fallback) and return token bundle."""
    username = username.strip()

    # Offline / AF_AUTH=off path
    if not is_auth_enabled():
        demo_accounts = {
            "amira": {"email": "amira@alphaforge.demo", "groups": []},
            "mateo": {"email": "mateo@alphaforge.demo", "groups": []},
            "robert": {"email": "robert@alphaforge.demo", "groups": []},
            "advisor": {"email": "advisor@alphaforge.demo", "groups": ["advisor"]},
        }
        if username in demo_accounts:
            acc = demo_accounts[username]
            user = User(
                user_id=username,
                username=username,
                email=acc["email"],
                groups=acc["groups"],
            )
            token = create_dev_token(user)
            return {
                "access_token": token,
                "id_token": token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "user": user.model_dump(),
            }
        # Allow custom dev username if password is provided
        if password:
            user = User(
                user_id=username,
                username=username,
                email=f"{username}@alphaforge.demo",
                groups=["advisor"] if username == "advisor" else [],
            )
            token = create_dev_token(user)
            return {
                "access_token": token,
                "id_token": token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "user": user.model_dump(),
            }
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    # AWS Cognito InitiateAuth
    try:
        profile = os.getenv("AWS_PROFILE")
        if profile:
            session = boto3.Session(profile_name=profile, region_name=COGNITO_REGION)
        else:
            session = boto3.Session(region_name=COGNITO_REGION)
        client = session.client("cognito-idp", region_name=COGNITO_REGION)

        resp = client.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
        )
        auth_res = resp.get("AuthenticationResult", {})
        id_token = auth_res.get("IdToken")
        access_token = auth_res.get("AccessToken")
        token_to_verify = id_token or access_token
        verified_user = verify_token(token_to_verify)

        return {
            "access_token": access_token,
            "id_token": id_token,
            "token_type": "Bearer",
            "expires_in": auth_res.get("ExpiresIn", 3600),
            "user": verified_user.model_dump(),
        }
    except client.exceptions.NotAuthorizedException as e:
        raise HTTPException(status_code=401, detail="Nom d'utilisateur ou mot de passe incorrect.") from e
    except client.exceptions.UserNotFoundException as e:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable.") from e
    except Exception as e:
        logger.exception("Cognito login error: %s", e)
        raise HTTPException(status_code=401, detail=f"Erreur d'authentification: {e}") from e


def extract_token_from_request(request: Request) -> str | None:
    """Extract token from Authorization header or 'token' query param."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :].strip()
    return request.query_params.get("token")


def get_current_user_from_request_or_none(request: Request) -> User | None:
    token = extract_token_from_request(request)
    if not token:
        return None
    try:
        return verify_token(token)
    except HTTPException:
        return None


def get_current_user_optional(
    request: Request,
    auth: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> User | None:
    token = auth.credentials if auth else request.query_params.get("token")
    if not token:
        return None
    return verify_token(token)


def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)] = None,
) -> User:
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentification requise pour cette opération.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_advisor(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_advisor:
        raise HTTPException(
            status_code=403,
            detail="Accès réservé aux conseillers enregistrés (groupe 'advisor').",
        )
    return user
