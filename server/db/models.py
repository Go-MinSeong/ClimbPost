import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from server.db.database import Base


def _uuid():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, nullable=True)
    provider = Column(String, nullable=False)  # "apple" | "google"
    created_at = Column(DateTime, default=_utcnow)

    upload_sessions = relationship("UploadSession", back_populates="user")
    device_tokens = relationship("DeviceToken", back_populates="user")


class Gym(Base):
    __tablename__ = "gyms"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    color_map = Column(JSON, nullable=True)

    upload_sessions = relationship("UploadSession", back_populates="gym")
    clips = relationship("Clip", back_populates="gym")


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    gym_id = Column(String, ForeignKey("gyms.id"), nullable=True)
    recorded_date = Column(DateTime, nullable=True)
    status = Column(String, default="uploading")  # uploading/analyzing/completed/failed
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="upload_sessions")
    gym = relationship("Gym", back_populates="upload_sessions")
    raw_videos = relationship("RawVideo", back_populates="session")
    jobs = relationship("Job", back_populates="session")


class RawVideo(Base):
    __tablename__ = "raw_videos"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("upload_sessions.id"), nullable=False)
    file_url = Column(String, nullable=True)
    duration_sec = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    session = relationship("UploadSession", back_populates="raw_videos")
    clips = relationship("Clip", back_populates="raw_video")


class Clip(Base):
    __tablename__ = "clips"

    id = Column(String, primary_key=True, default=_uuid)
    raw_video_id = Column(String, ForeignKey("raw_videos.id"), nullable=False)
    gym_id = Column(String, ForeignKey("gyms.id"), nullable=True)
    start_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    duration_sec = Column(Float, nullable=True)
    difficulty = Column(String, nullable=True)
    tape_color = Column(String, nullable=True)
    result = Column(String, nullable=True)  # "success" | "fail"
    is_me = Column(Boolean, default=False)
    thumbnail_url = Column(String, nullable=True)
    clip_url = Column(String, nullable=True)
    edited_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    raw_video = relationship("RawVideo", back_populates="clips")
    gym = relationship("Gym", back_populates="clips")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("upload_sessions.id"), nullable=False)
    status = Column(String, default="pending")  # pending/processing/completed/failed
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    session = relationship("UploadSession", back_populates="jobs")


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="device_tokens")


class InstagramAccount(Base):
    __tablename__ = "instagram_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    ig_user_id = Column(String, nullable=False)  # Instagram Business Account ID
    ig_username = Column(String, nullable=True)
    ig_profile_picture = Column(String, nullable=True)
    page_id = Column(String, nullable=False)  # Facebook Page ID
    page_access_token = Column(String, nullable=False)  # Never-expiring page token
    long_lived_user_token = Column(String, nullable=True)  # 60-day user token
    user_token_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class InstagramPublishJob(Base):
    __tablename__ = "instagram_publish_jobs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    clip_ids = Column(JSON, nullable=False)
    caption = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending/uploading/processing/published/failed
    error_message = Column(String, nullable=True)
    container_ids = Column(JSON, nullable=True)
    carousel_container_id = Column(String, nullable=True)
    ig_media_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
