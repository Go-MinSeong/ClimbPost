from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# --- Auth ---

class LoginRequest(BaseModel):
    provider: str  # "apple" | "google"
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    user_id: str
    email: Optional[str] = None
    provider: str


# --- Gym ---

class GymResponse(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    color_map: Optional[dict] = None

    model_config = {"from_attributes": True}


# --- Upload Session ---

class UploadSessionCreate(BaseModel):
    gym_id: Optional[str] = None
    recorded_date: Optional[datetime] = None


class UploadSessionResponse(BaseModel):
    id: str
    user_id: str
    gym_id: Optional[str] = None
    recorded_date: Optional[datetime] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Raw Video ---

class RawVideoResponse(BaseModel):
    id: str
    session_id: str
    file_url: Optional[str] = None
    duration_sec: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Clip ---

class ClipResponse(BaseModel):
    id: str
    raw_video_id: str
    gym_id: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    duration_sec: Optional[float] = None
    difficulty: Optional[str] = None
    tape_color: Optional[str] = None
    result: Optional[str] = None
    is_me: bool = False
    thumbnail_url: Optional[str] = None
    clip_url: Optional[str] = None
    edited_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Job ---

class JobResponse(BaseModel):
    id: str
    session_id: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
