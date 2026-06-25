"""
app/auth.py — Firebase ID token verification using python-jose.

Design:
- Does NOT use the Firebase Admin SDK (avoids heavy dependency + service account file)
- Fetches Google's public X.509 certificates and verifies JWT signature directly
- Caches certificates for 5 minutes (they rotate ~daily, so 5min is safe and cheap)
- Validates all required Firebase JWT claims: iss, aud, exp, iat, sub
- Provides both get_current_user (required auth) and get_optional_user (optional auth)

Security notes:
- FIREBASE_PUBLIC_KEYS_URL serves RSA public keys in X.509 PEM format
- jose.jwt.decode verifies both signature and standard time claims (exp/iat)
- iss and aud are checked explicitly against our firebase_project_id
- sub (uid) must be a non-empty string — empty sub is a Firebase anomaly

References:
  https://firebase.google.com/docs/auth/admin/verify-id-tokens#verify_id_tokens_using_a_third-party_jwt_library
"""
import logging
import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)

# ── Firebase public key endpoint ──────────────────────────────────────────────
# Returns a JSON object mapping key-id → PEM-encoded X.509 certificate.
# Google rotates these roughly every 24 hours.
FIREBASE_PUBLIC_KEYS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)

# ── In-memory key cache ───────────────────────────────────────────────────────
# Structure: {"keys": {kid: pem_cert, ...}, "fetched_at": float}
# Intentionally simple — a single-server tool doesn't need Redis for this.
_key_cache: dict[str, Any] = {
    "keys": {},
    "fetched_at": 0.0,
}

_CACHE_TTL_SECONDS = 300  # 5 minutes — well within Google's rotation window

# ── Key fetching ──────────────────────────────────────────────────────────────

async def get_firebase_public_keys() -> dict[str, str]:
    """
    Return the current Firebase public signing keys as {kid: pem_cert}.

    Uses a 5-minute in-memory cache to avoid hammering Google's endpoint
    on every request. The cache is keyed by fetch timestamp.
    """
    now = time.monotonic()
    if now - _key_cache["fetched_at"] < _CACHE_TTL_SECONDS and _key_cache["keys"]:
        return _key_cache["keys"]  # type: ignore[return-value]

    logger.debug("Refreshing Firebase public keys from Google")
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(FIREBASE_PUBLIC_KEYS_URL)

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to fetch Firebase public keys: HTTP {response.status_code}",
        )

    keys = response.json()
    if not isinstance(keys, dict) or not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase public keys response was empty or malformed",
        )

    _key_cache["keys"] = keys
    _key_cache["fetched_at"] = now
    logger.debug("Firebase public keys refreshed — %d keys cached", len(keys))
    return keys  # type: ignore[return-value]


# ── Token verification ────────────────────────────────────────────────────────

async def verify_firebase_token(token: str) -> dict[str, Any]:
    """
    Verify a Firebase ID token and return the decoded JWT payload.

    Validation steps (per Firebase docs):
    1. Fetch current public keys from Google
    2. Decode the JWT header to identify which key was used (kid)
    3. Verify signature using the matching public key
    4. Check iss: must be https://securetoken.google.com/<project_id>
    5. Check aud: must be <project_id>
    6. exp/iat are verified automatically by jose.jwt.decode
    7. Check sub (uid): must be non-empty string

    Raises:
        HTTPException(401): On any verification failure — message is safe to surface
    """
    # Step 1: Get public keys
    public_keys = await get_firebase_public_keys()

    # Step 2: Peek at the JWT header to find the key ID (kid)
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token format: {exc}",
        ) from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token header missing 'kid' field",
        )

    if kid not in public_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signed with unknown key ID — your token may be expired",
        )

    pem_cert = public_keys[kid]

    # Step 3–6: Verify signature + standard claims
    expected_issuer = f"https://securetoken.google.com/{settings.firebase_project_id}"
    try:
        payload = jwt.decode(
            token,
            pem_cert,
            algorithms=["RS256"],
            audience=settings.firebase_project_id,
            issuer=expected_issuer,
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
    except JWTError as exc:
        logger.error(f"JWT Verification Error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {exc}",
        ) from exc

    # Step 7: Validate sub (Firebase UID)
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing or invalid 'sub' (uid) claim",
        )

    return payload


# ── FastAPI security scheme ───────────────────────────────────────────────────
# auto_error=False so we can handle missing credentials ourselves (better errors)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict[str, Any]:
    """
    FastAPI dependency: require a valid Firebase ID token.

    Usage:
        @router.get("/protected")
        async def route(user: dict = Depends(get_current_user)):
            uid = user["sub"]
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header (expected 'Bearer <token>')",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await verify_firebase_token(credentials.credentials)

async def get_user_from_query(token: str | None = None) -> dict[str, Any]:
    """
    FastAPI dependency: require a valid Firebase ID token from the query string.
    Used for <iframe> and <video> tags that cannot send Authorization headers.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'token' query parameter",
        )
    return await verify_firebase_token(token)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict[str, Any] | None:
    """
    FastAPI dependency: accept a valid Firebase ID token but don't require one.

    Returns the decoded payload if a valid token is provided, None otherwise.
    Invalid tokens still return None (not an error) — useful for public routes
    that show extra info when authenticated.
    """
    if credentials is None:
        return None
    try:
        return await verify_firebase_token(credentials.credentials)
    except HTTPException:
        return None
