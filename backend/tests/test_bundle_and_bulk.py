import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.bundle import SmsBundle
from app.services.bundle_service import (
    get_or_create_active_bundle,
    check_and_deduct_credits,
    topup_bundle,
    get_bundle_summary,
)
from app.services.message_service import calculate_sms_parts, format_message_with_brand

client = TestClient(app)


def test_format_message_with_brand():
    # 1. Custom brand specified
    res1 = format_message_with_brand("Hello world", "EDUSPHERE")
    assert res1 == "[EDUSPHERE] Hello world"

    # 2. Already bracketed brand
    res2 = format_message_with_brand("[EDUSPHERE] Hello world", "EDUSPHERE")
    assert res2 == "[EDUSPHERE] Hello world"

    # 3. Colon prefix
    res3 = format_message_with_brand("EDUSPHERE: Code is 1234", "EDUSPHERE")
    assert res3 == "EDUSPHERE: Code is 1234"

    # 4. No brand
    res4 = format_message_with_brand("Hello world", None)
    assert res4 == "Hello world"


def test_bundle_service_flow(db_session: Session):
    # 1. Default bundle creation
    bundle = get_or_create_active_bundle(db_session)
    assert bundle.available_credits >= 5000
    assert bundle.is_active is True

    # 2. Deduct credits
    initial_credits = bundle.available_credits
    deducted = check_and_deduct_credits(db_session, 5)
    assert deducted.available_credits == initial_credits - 5
    assert deducted.used_credits >= 5

    # 3. Top-up credits
    topped = topup_bundle(db_session, credits_to_add=1000, extend_days=60, plan_name="Enterprise VIP")
    assert topped.available_credits == initial_credits - 5 + 1000
    assert topped.plan_name == "Enterprise VIP"

    # 4. Summary
    summary = get_bundle_summary(db_session)
    assert summary["available_credits"] == topped.available_credits
    assert summary["days_left"] >= 30
    assert summary["is_expired"] is False


def test_bundle_expiration_enforcement(db_session: Session):
    bundle = get_or_create_active_bundle(db_session)
    # Set to past date
    bundle.expires_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.commit()

    with pytest.raises(ValueError, match="limeisha"):
        check_and_deduct_credits(db_session, 1)

    # Reset for next tests
    bundle.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    db_session.commit()


def test_bulk_sms_api_endpoint(client: TestClient, db_session: Session):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    admin_token = login_res.json()["access_token"]

    # Test bulk message submission with custom sender_name, sim_slot and anti-spam delay
    recipients = ["+255712345678", "+255789123456", "0712345678", "+255712345678"]  # includes duplicate and local 07...
    payload = {
        "recipients": recipients,
        "message": "Important meeting reminder from Edusphere Academy.",
        "sender_name": "EDUSPHERE",
        "sim_slot": 1,
        "anti_spam_delay": 5.0,
        "randomize_jitter": True,
    }

    res = client.post(
        "/api/v1/messages/bulk",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["total_recipients"] == 4
    assert data["valid_recipients"] == 2  # 0712345678 and +255712345678 are identical, so duplicates removed
    assert data["queued_messages"] == 2
    assert data["credits_deducted"] == 2
    assert "Anti-spam carrier protection enabled" in data["message"]


def test_admin_bundle_endpoints(client: TestClient):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    admin_token = login_res.json()["access_token"]

    # 1. GET /api/v1/admin/bundle
    res = client.get(
        "/api/v1/admin/bundle",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "available_credits" in data
    assert "days_left" in data
    assert "percent_remaining" in data

    # 2. POST /api/v1/admin/bundle/topup
    topup_payload = {
        "credits": 2500,
        "extend_days": 45,
        "plan_name": "VIP Business Plan",
    }
    topup_res = client.post(
        "/api/v1/admin/bundle/topup",
        json=topup_payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert topup_res.status_code == 200
    topup_data = topup_res.json()
    assert topup_data["plan_name"] == "VIP Business Plan"
    assert topup_data["available_credits"] >= 2500
