"""Instagram OAuth: exchange auth code for tokens + find IG Business Account."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from server.auth.service import get_current_user
from server.config.settings import FB_APP_ID, FB_APP_SECRET, FB_REDIRECT_URI
from server.db.database import get_db
from server.db.models import User, InstagramAccount

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/instagram", tags=["instagram-auth"])

GRAPH_API = "https://graph.facebook.com/v21.0"


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class ExchangeRequest(BaseModel):
    code: str


class InstagramAccountResponse(BaseModel):
    ig_username: str | None
    ig_profile_picture: str | None
    connected: bool


class ConnectInfoResponse(BaseModel):
    fb_app_id: str
    redirect_uri: str
    scopes: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/connect-info", response_model=ConnectInfoResponse)
async def get_connect_info():
    """Return the Facebook App ID and OAuth config for the iOS app to start the flow."""
    if not FB_APP_ID:
        raise HTTPException(status_code=503, detail="FB_APP_ID not configured")
    return ConnectInfoResponse(
        fb_app_id=FB_APP_ID,
        redirect_uri=FB_REDIRECT_URI,
        scopes="instagram_basic,instagram_content_publish,pages_read_engagement,pages_show_list",
    )


@router.post("/exchange", response_model=InstagramAccountResponse)
async def exchange_code(
    body: ExchangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Exchange Facebook auth code for Instagram Business Account tokens.

    Full chain: code → short-lived token → long-lived token → page token → IG user ID.
    """
    if not FB_APP_ID or not FB_APP_SECRET:
        raise HTTPException(status_code=503, detail="Facebook App not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Auth code → short-lived user token
        resp = await client.get(f"{GRAPH_API}/oauth/access_token", params={
            "client_id": FB_APP_ID,
            "client_secret": FB_APP_SECRET,
            "redirect_uri": FB_REDIRECT_URI,
            "code": body.code,
        })
        if resp.status_code != 200:
            logger.error("Token exchange failed: %s", resp.text)
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.json().get('error', {}).get('message', resp.text)}")
        short_token = resp.json()["access_token"]

        # Step 2: Short-lived → long-lived user token (60 days)
        resp = await client.get(f"{GRAPH_API}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": FB_APP_ID,
            "client_secret": FB_APP_SECRET,
            "fb_exchange_token": short_token,
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Long-lived token exchange failed")
        data = resp.json()
        long_token = data["access_token"]
        expires_in = data.get("expires_in", 5184000)

        # Step 3: Get user's Facebook Pages
        resp = await client.get(f"{GRAPH_API}/me/accounts", params={
            "access_token": long_token,
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get Facebook Pages")
        pages = resp.json().get("data", [])

        if not pages:
            raise HTTPException(
                status_code=400,
                detail="Facebook 페이지가 없습니다. Instagram Business 계정과 연결된 Facebook 페이지가 필요합니다.",
            )

        # Step 4: Find Instagram Business Account on each page
        ig_user_id = None
        page_token = None
        page_id = None

        for page in pages:
            resp = await client.get(
                f"{GRAPH_API}/{page['id']}",
                params={
                    "fields": "instagram_business_account",
                    "access_token": page["access_token"],
                },
            )
            ig_data = resp.json().get("instagram_business_account")
            if ig_data:
                ig_user_id = ig_data["id"]
                page_token = page["access_token"]  # never-expiring when from long-lived user token
                page_id = page["id"]
                break

        if not ig_user_id:
            raise HTTPException(
                status_code=400,
                detail="Instagram Business/Creator 계정을 찾을 수 없습니다. Instagram 앱에서 비즈니스 계정으로 전환하고 Facebook 페이지와 연결하세요.",
            )

        # Step 5: Get IG profile info
        resp = await client.get(
            f"{GRAPH_API}/{ig_user_id}",
            params={
                "fields": "id,username,profile_picture_url",
                "access_token": page_token,
            },
        )
        ig_profile = resp.json()
        ig_username = ig_profile.get("username")
        ig_picture = ig_profile.get("profile_picture_url")

    # Step 6: Store in DB (upsert)
    existing = db.query(InstagramAccount).filter(InstagramAccount.user_id == user.id).first()
    if existing:
        existing.ig_user_id = ig_user_id
        existing.ig_username = ig_username
        existing.ig_profile_picture = ig_picture
        existing.page_id = page_id
        existing.page_access_token = page_token
        existing.long_lived_user_token = long_token
        existing.user_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    else:
        account = InstagramAccount(
            user_id=user.id,
            ig_user_id=ig_user_id,
            ig_username=ig_username,
            ig_profile_picture=ig_picture,
            page_id=page_id,
            page_access_token=page_token,
            long_lived_user_token=long_token,
            user_token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )
        db.add(account)
    db.commit()

    logger.info("Instagram connected for user %s: @%s (IG ID: %s)", user.id, ig_username, ig_user_id)

    return InstagramAccountResponse(
        ig_username=ig_username,
        ig_profile_picture=ig_picture,
        connected=True,
    )


@router.get("/status", response_model=InstagramAccountResponse)
async def get_instagram_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if user has connected Instagram account."""
    account = db.query(InstagramAccount).filter(InstagramAccount.user_id == user.id).first()
    if not account:
        return InstagramAccountResponse(ig_username=None, ig_profile_picture=None, connected=False)
    return InstagramAccountResponse(
        ig_username=account.ig_username,
        ig_profile_picture=account.ig_profile_picture,
        connected=True,
    )


@router.delete("/disconnect")
async def disconnect_instagram(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disconnect Instagram account."""
    account = db.query(InstagramAccount).filter(InstagramAccount.user_id == user.id).first()
    if account:
        db.delete(account)
        db.commit()
    return {"disconnected": True}
