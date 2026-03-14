import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.db.database import Base, get_db
from server.db.models import User
from server.auth.service import create_jwt
from server.main import app

TEST_DATABASE_URL = "sqlite://"  # in-memory


@pytest.fixture
def db_session():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def create_test_user_token(db_session, email="test@test.com", provider="apple"):
    """Create a user in the DB and return (user, jwt_token)."""
    user = User(provider=provider, email=email)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_jwt(user.id)
    return user, token


@pytest.fixture
def auth_header(db_session):
    user, token = create_test_user_token(db_session)
    return {"Authorization": f"Bearer {token}"}, user
