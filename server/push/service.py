import json
import logging
import time
from typing import Optional

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from server.auth.service import get_current_user
from server.config.settings import APNS_KEY_PATH, APNS_KEY_ID, APNS_TEAM_ID
from server.db.database import get_db
from server.db.models import User, DeviceToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["push"])

APNS_HOST = "https://api.push.apple.com"
APNS_DEV_HOST = "https://api.sandbox.push.apple.com"


class RegisterTokenRequest(BaseModel):
    device_token: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_device_token(
    body: RegisterTokenRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register or update a device token for push notifications."""
    existing = db.query(DeviceToken).filter(
        DeviceToken.user_id == user.id,
        DeviceToken.token == body.device_token,
    ).first()

    if existing:
        return {"status": "already_registered"}

    token = DeviceToken(user_id=user.id, token=body.device_token)
    db.add(token)
    db.commit()
    return {"status": "registered"}


def _create_apns_jwt() -> Optional[str]:
    """Create a JWT for APNs authentication."""
    if not APNS_KEY_PATH or not APNS_KEY_ID or not APNS_TEAM_ID:
        return None

    try:
        with open(APNS_KEY_PATH, "r") as f:
            private_key = f.read()
    except FileNotFoundError:
        logger.warning("APNs key file not found: %s", APNS_KEY_PATH)
        return None

    headers = {"alg": "ES256", "kid": APNS_KEY_ID}
    payload = {"iss": APNS_TEAM_ID, "iat": int(time.time())}
    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


async def send_push(user_id: str, title: str, body: str, db: Session) -> None:
    """Send push notification to all devices registered by a user."""
    tokens = db.query(DeviceToken).filter(DeviceToken.user_id == user_id).all()
    if not tokens:
        logger.info("No device tokens found for user %s", user_id)
        return

    apns_token = _create_apns_jwt()
    if not apns_token:
        logger.warning("APNs not configured, skipping push for user %s", user_id)
        return

    payload = json.dumps({
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        }
    })

    async with httpx.AsyncClient(http2=True) as client:
        for dt in tokens:
            try:
                resp = await client.post(
                    f"{APNS_DEV_HOST}/3/device/{dt.token}",
                    content=payload,
                    headers={
                        "authorization": f"bearer {apns_token}",
                        "apns-topic": "com.climbpost.app",
                        "apns-push-type": "alert",
                    },
                )
                if resp.status_code != 200:
                    logger.warning("APNs push failed for token %s: %s", dt.token[:8], resp.text)
            except Exception:
                logger.exception("Failed to send push to token %s", dt.token[:8])
