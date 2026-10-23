import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.database import Base, get_db
from app.core.security import generate_api_key, generate_device_token
from app.models.api_key import ApiKey
from app.models.device import GatewayDevice
from app.main import app

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def valid_api_key(db_session):
    raw_key, prefix, key_hash = generate_api_key(prefix="sms_live_")
    key = ApiKey(
        name="Test Full Client",
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=["sms:send", "sms:read", "incoming:read", "webhooks:manage"],
        rate_limit=100,
    )
    db_session.add(key)
    db_session.commit()
    db_session.refresh(key)
    return {"raw_key": raw_key, "key": key}


@pytest.fixture(scope="function")
def readonly_api_key(db_session):
    raw_key, prefix, key_hash = generate_api_key(prefix="sms_live_")
    key = ApiKey(
        name="Readonly Client",
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=["sms:read"],
        rate_limit=100,
    )
    db_session.add(key)
    db_session.commit()
    db_session.refresh(key)
    return {"raw_key": raw_key, "key": key}


@pytest.fixture(scope="function")
def paired_device(db_session):
    raw_token, token_hash = generate_device_token()
    device = GatewayDevice(
        name="Test Phone",
        model="Pixel 6",
        os_version="Android 14",
        app_version="1.0.0",
        device_token_hash=token_hash,
        sim_ready=True,
        phone_number="+255712000000",
        is_online=True,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return {"raw_token": raw_token, "device": device}
