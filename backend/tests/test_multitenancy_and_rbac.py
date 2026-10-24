import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.tenant import Tenant, User
from app.models.device import GatewayDevice
from app.models.bundle import SmsBundle
from app.models.credit_transaction import CreditTransaction
from app.core.security import hash_password, generate_api_key
from app.models.api_key import ApiKey
from app.services.device_service import get_next_job, set_kill_switch, report_send_result
from app.schemas.device import DeviceSendResultRequest


def test_tenant_creation_and_user_auth(client, db_session: Session):
    # 1. Login as Super Admin
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    assert login_res.status_code == 200
    super_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {super_token}"}

    # 2. Create Tenant
    tenant_payload = {
        "name": "Kigali Logistics Ltd",
        "slug": "kigali-logistics",
        "can_use_shared_devices": True,
        "require_bulk_approval_threshold": 50,
        "allowed_sender_names": ["KIGALI_LOG"],
        "daily_sms_limit": 5000,
    }
    create_t_res = client.post("/api/v1/admin/tenants", json=tenant_payload, headers=headers)
    assert create_t_res.status_code == 201
    tenant_data = create_t_res.json()
    tenant_id = tenant_data["id"]

    # 3. Create Tenant Admin User
    user_payload = {
        "email": "manager@kigalilogistics.com",
        "password": "SecurePassword123!",
        "full_name": "Juma Bakari",
        "role": "tenant_admin",
        "tenant_id": tenant_id,
    }
    create_u_res = client.post("/api/v1/admin/users", json=user_payload, headers=headers)
    assert create_u_res.status_code == 201
    user_data = create_u_res.json()
    assert user_data["email"] == "manager@kigalilogistics.com"

    # 4. Login as Tenant User
    t_login = client.post(
        "/api/v1/auth/login",
        json={"username": "manager@kigalilogistics.com", "password": "SecurePassword123!"},
    )
    assert t_login.status_code == 200
    t_data = t_login.json()
    assert t_data["user"]["tenant_id"] == tenant_id
    assert t_data["user"]["role"] == "tenant_admin"
    assert t_data["user"]["tenant_name"] == "Kigali Logistics Ltd"


def test_api_key_ip_whitelisting(client, db_session: Session):
    # Create an API Key with CIDR whitelist: 192.168.1.0/24 and 10.0.0.5
    raw_key, prefix, key_hash = generate_api_key(prefix="gw_")
    key = ApiKey(
        name="Secured IP Key",
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=["sms:send", "sms:read"],
        rate_limit=100,
        allowed_ips="192.168.1.0/24, 10.0.0.5",
        is_active=True,
    )
    db_session.add(key)
    db_session.commit()

    # 1. Request from non-whitelisted IP (e.g. 203.0.113.42)
    res_blocked = client.get(
        "/api/v1/messages",
        headers={"Authorization": f"Bearer {raw_key}", "X-Forwarded-For": "203.0.113.42"},
    )
    assert res_blocked.status_code == 403
    assert "not permitted by API key IP whitelist" in res_blocked.json()["detail"]

    # 2. Request from permitted IP in 192.168.1.0/24 subnet
    res_allowed = client.get(
        "/api/v1/messages",
        headers={"Authorization": f"Bearer {raw_key}", "X-Forwarded-For": "192.168.1.55"},
    )
    assert res_allowed.status_code == 200


def test_auto_refund_on_terminal_failure(client, db_session: Session):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    admin_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Check initial bundle credits
    bundle_res = client.get("/api/v1/admin/bundle", headers=headers)
    initial_credits = bundle_res.json()["available_credits"]

    # 2. Submit SMS
    msg_res = client.post(
        "/api/v1/messages",
        json={"to": "+255712334455", "message": "Transactional verification code: 9942"},
        headers=headers,
    )
    assert msg_res.status_code == 201
    msg_id = msg_res.json()["id"]

    # Balance decreased by 1
    bundle_after = client.get("/api/v1/admin/bundle", headers=headers).json()
    assert bundle_after["available_credits"] == initial_credits - 1

    # 3. Simulate Device leasing job
    device = GatewayDevice(
        name="AutoRefundPhone",
        device_token_hash="hash_auto_refund_dev",
        is_online=True,
    )
    db_session.add(device)
    db_session.commit()

    leased_job = get_next_job(db_session, device)
    assert leased_job is not None

    # 4. Device reports terminal failure (e.g. out of service / carrier rejection)
    report_send_result(
        db_session,
        device=device,
        job_id=msg_id,
        req=DeviceSendResultRequest(
            status="failed",
            error_message="RESULT_ERROR_GENERIC_FAILURE: Insufficient SIM airtime",
            timestamp=datetime.now(timezone.utc),
        ),
    )

    # 5. Verify automatic credit refund back to the bundle!
    bundle_refunded = client.get("/api/v1/admin/bundle", headers=headers).json()
    assert bundle_refunded["available_credits"] == initial_credits

    # 6. Verify immutable credit transaction was recorded in ledger
    tx = (
        db_session.query(CreditTransaction)
        .filter(CreditTransaction.message_id == msg_id, CreditTransaction.tx_type == "refund")
        .first()
    )
    assert tx is not None
    assert tx.amount == 1
    assert "Auto-refund" in tx.reason


def test_emergency_kill_switch_halting(db_session: Session):
    device = GatewayDevice(
        name="KillSwitchTestPhone",
        device_token_hash="hash_kill_switch_test",
        is_online=True,
    )
    db_session.add(device)
    db_session.commit()

    # 1. Enable Global Kill Switch
    set_kill_switch(True)

    # 2. Attempt to lease job
    job = get_next_job(db_session, device)
    assert job is None  # Paused!

    # 3. Disable Kill Switch
    set_kill_switch(False)
