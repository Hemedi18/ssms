from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator
from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they do not exist."""
    # Import all models to ensure they are registered with Base.metadata
    from app.models.api_key import ApiKey
    from app.models.device import GatewayDevice, PairingCode
    from app.models.message import Message, MessageEvent
    from app.models.incoming_message import IncomingMessage
    from app.models.webhook import WebhookSubscription, WebhookDelivery
    from app.models.audit import AuditEvent

    Base.metadata.create_all(bind=engine)
