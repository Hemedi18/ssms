from sqlalchemy import create_engine, text
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
    """Create all tables and perform defensive schema migrations."""
    # Import all models to ensure registration in Base.metadata
    from app.models.tenant import Tenant, User
    from app.models.api_key import ApiKey
    from app.models.device import GatewayDevice, PairingCode
    from app.models.message import Message, MessageEvent
    from app.models.incoming_message import IncomingMessage
    from app.models.webhook import WebhookSubscription, WebhookDelivery
    from app.models.audit import AuditEvent
    from app.models.bundle import SmsBundle
    from app.models.credit_transaction import CreditTransaction
    from app.models.dnd_and_moderation import DndBlacklist, ContentModerationRule

    Base.metadata.create_all(bind=engine)

    # Defensive schema updates for existing tables
    try:
        with engine.connect() as conn:
            if settings.DATABASE_URL.startswith("sqlite"):
                # Helper to add column if missing
                def _add_col_if_missing(table_name: str, col_name: str, col_def: str):
                    try:
                        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
                        existing_cols = {row[1] for row in rows}
                        if col_name not in existing_cols:
                            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))
                    except Exception:
                        pass

                # Messages
                _add_col_if_missing("messages", "tenant_id", "VARCHAR(36)")
                _add_col_if_missing("messages", "sender_name", "VARCHAR(50)")
                _add_col_if_missing("messages", "sim_slot", "INTEGER")
                _add_col_if_missing("messages", "original_body", "TEXT")
                _add_col_if_missing("messages", "message_type", "VARCHAR(20) DEFAULT 'transactional'")
                _add_col_if_missing("messages", "priority", "INTEGER DEFAULT 10")
                _add_col_if_missing("messages", "encoding", "VARCHAR(20) DEFAULT 'GSM_7BIT'")
                _add_col_if_missing("messages", "detected_mno", "VARCHAR(30) DEFAULT 'UNKNOWN'")
                _add_col_if_missing("messages", "modified_by_admin_id", "VARCHAR(36)")
                _add_col_if_missing("messages", "admin_notes", "TEXT")
                _add_col_if_missing("messages", "scheduled_for", "TIMESTAMP")

                # Gateway devices
                _add_col_if_missing("gateway_devices", "tenant_id", "VARCHAR(36)")
                _add_col_if_missing("gateway_devices", "is_shared_pool", "BOOLEAN DEFAULT 1")
                _add_col_if_missing("gateway_devices", "max_sms_per_30_min", "INTEGER DEFAULT 28")
                _add_col_if_missing("gateway_devices", "sim_slots_telemetry", "JSON")

                # Pairing codes
                _add_col_if_missing("pairing_codes", "tenant_id", "VARCHAR(36)")

                # SMS Bundles
                _add_col_if_missing("sms_bundles", "tenant_id", "VARCHAR(36)")

                # API Keys
                _add_col_if_missing("api_keys", "tenant_id", "VARCHAR(36)")
                _add_col_if_missing("api_keys", "allowed_ips", "TEXT")

                # Incoming messages
                _add_col_if_missing("incoming_messages", "tenant_id", "VARCHAR(36)")

                # Webhook subscriptions
                _add_col_if_missing("webhook_subscriptions", "tenant_id", "VARCHAR(36)")

                conn.commit()
    except Exception:
        pass

    # Seed default tenant and super admin user if none exists
    try:
        from app.core.security import hash_password
        db = SessionLocal()
        try:
            default_tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
            if not default_tenant:
                default_tenant = Tenant(
                    name="Default Organization",
                    slug="default",
                    status="active",
                    can_use_shared_devices=True,
                    require_bulk_approval_threshold=200,
                    allowed_sender_names=["EDUSPHERE", "SMS_GATEWAY"],
                    daily_sms_limit=10000,
                )
                db.add(default_tenant)
                db.commit()
                db.refresh(default_tenant)

            admin_user = db.query(User).filter(User.email == "admin@smsgateway.local").first()
            if not admin_user:
                admin_user = User(
                    tenant_id=default_tenant.id,
                    email="admin@smsgateway.local",
                    password_hash=hash_password(settings.ADMIN_PASSWORD),
                    full_name="Super Administrator",
                    role="super_admin",
                    is_active=True,
                )
                db.add(admin_user)
                db.commit()
        finally:
            db.close()
    except Exception:
        pass
