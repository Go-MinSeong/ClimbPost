from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from server.config.settings import DATABASE_URL


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    from server.db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
