from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from server.db.database import get_db
from server.db.models import User
from server.db.schemas import LoginRequest, TokenResponse, RefreshResponse, UserResponse
from server.auth.service import (
    verify_apple_token,
    verify_google_token,
    create_jwt,
    get_current_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with Apple or Google ID token and return a JWT."""
    if body.provider == "apple":
        identity = await verify_apple_token(body.id_token)
    elif body.provider == "google":
        identity = await verify_google_token(body.id_token)
    else:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {body.provider}",
        )

    provider_sub = identity["sub"]
    email = identity.get("email")

    # Find or create user by provider + sub
    user = db.query(User).filter(
        User.provider == body.provider,
        User.email == email,
    ).first()

    if not user:
        user = User(
            provider=body.provider,
            email=email,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_jwt(user.id)
    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(user: User = Depends(get_current_user)):
    """Refresh the JWT token."""
    access_token = create_jwt(user.id)
    return RefreshResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    """Get current user info."""
    return UserResponse(
        user_id=user.id,
        email=user.email,
        provider=user.provider,
    )
