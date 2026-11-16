"""Amazon Cognito authentication, JWT verification, and FastAPI dependencies (PRD C-14, #128)."""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import ssl
import threading
from typing import Annotated, Any

import boto3
import certifi
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
            ssl_ctx = None
            try:
                ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                try:
                    ssl_ctx = ssl.create_default_context()
                except Exception:
                    ssl_ctx = None
            _jwks_client = PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=10, ssl_context=ssl_ctx)
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


DEMO_PERSONA_IDS: frozenset[str] = frozenset({"amira", "mateo", "robert"})


def verify_token(token: str) -> User:
    """Verify Cognito or Dev JWT token and return User object. Raises HTTPException 401 on failure."""
    if not token:
        raise HTTPException(status_code=401, detail="Jeton d'authentification manquant")

    # Fixed session tokens of the three fictional demo personas, and nothing else: any other
    # "demo-..." string (demo-advisor, demo-<real username>, "demo-") is rejected and never
    # grants a group. The match is exact (no case folding, no trimming).
    if token.startswith("demo-"):
        demo_id = token[5:]
        if demo_id in DEMO_PERSONA_IDS:
            return User(
                user_id=f"demo-{demo_id}",
                username=demo_id.capitalize(),
                email=f"{demo_id}@alphaforge.demo",
                groups=[],
            )
        raise HTTPException(status_code=401, detail="Jeton de démonstration inconnu")

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

        if alg != "RS256":
            # Locally signed dev tokens use a secret that is in the repository: never valid here.
            raise ValueError("unsupported token algorithm")
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


def _dev_bundle(user: User) -> dict[str, Any]:
    token = create_dev_token(user)
    return {
        "access_token": token,
        "id_token": token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "user": user.model_dump(),
    }


def register_user(username: str, password: str, email: str | None = None) -> dict[str, Any]:
    """Create an account: Cognito sign-up when auth is on, a dev token when it is off.

    A failed sign-up is an error. It never falls back to a locally signed token, which would
    let anyone obtain a session for an existing username.
    """
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", username):
        raise HTTPException(
            status_code=400,
            detail="Nom d'utilisateur invalide (3 à 64 caractères : lettres, chiffres, . _ -).",
        )
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit comporter au moins 8 caractères.")

    if not is_auth_enabled():
        # Dev mode only: no group is ever granted at registration.
        return _dev_bundle(User(user_id=username, username=username, email=email or f"{username}@alphaforge.demo"))

    profile = os.getenv("AWS_PROFILE")
    session = (
        boto3.Session(profile_name=profile, region_name=COGNITO_REGION)
        if profile
        else boto3.Session(region_name=COGNITO_REGION)
    )
    client = session.client("cognito-idp", region_name=COGNITO_REGION)
    try:
        resp = client.sign_up(
            ClientId=COGNITO_CLIENT_ID,
            Username=username,
            Password=password,
            UserAttributes=[{"Name": "email", "Value": email}] if email else [],
        )
    except client.exceptions.UsernameExistsException as e:
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur est déjà pris.") from e
    except (client.exceptions.InvalidPasswordException, client.exceptions.InvalidParameterException) as e:
        raise HTTPException(
            status_code=400,
            detail="Mot de passe ou courriel refusé : 8 caractères minimum, avec majuscule, minuscule, "
            "chiffre et symbole.",
        ) from e
    except Exception as e:
        logger.warning("Cognito sign_up failed: %s", e)
        raise HTTPException(status_code=503, detail="La création de compte est indisponible pour le moment.") from e
    if not resp.get("UserConfirmed"):
        # Demo pool: the email is optional and unverified, so the server confirms the account.
        try:
            client.admin_confirm_sign_up(UserPoolId=COGNITO_USER_POOL_ID, Username=username)
        except Exception as e:
            logger.warning("Cognito admin_confirm_sign_up failed: %s", e)
            raise HTTPException(
                status_code=403,
                detail="Compte créé, mais il doit être confirmé avant la première connexion.",
            ) from e
    return authenticate_user(username, password)


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
