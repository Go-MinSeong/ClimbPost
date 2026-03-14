from datetime import datetime, timedelta, timezone

import httpx
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from server.config.settings import (
    JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_DAYS,
    APPLE_CLIENT_ID, GOOGLE_CLIENT_ID,
)
from server.db.database import get_db
from server.db.models import User

security = HTTPBearer()

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


async def verify_apple_token(id_token: str) -> dict:
    """Verify Apple Sign-In JWT using Apple's public keys."""
    try:
        jwks_client = PyJWKClient(APPLE_JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=APPLE_CLIENT_ID,
            issuer="https://appleid.apple.com",
        )
        return {
            "sub": payload["sub"],
            "email": payload.get("email"),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Apple token: {e}",
        )


async def verify_google_token(id_token: str) -> dict:
    """Verify Google Sign-In token via Google's tokeninfo API."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                GOOGLE_TOKENINFO_URL,
                params={"id_token": id_token},
            )
            resp.raise_for_status()
            payload = resp.json()

        if GOOGLE_CLIENT_ID and payload.get("aud") != GOOGLE_CLIENT_ID:
            raise ValueError("Audience mismatch")

        return {
            "sub": payload["sub"],
            "email": payload.get("email"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google token: {e}",
        )


def create_jwt(user_id: str) -> str:
    """Create a JWT access token."""
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: extract and validate user from JWT Bearer token."""
    payload = decode_jwt(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
