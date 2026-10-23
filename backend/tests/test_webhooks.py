import json
import pytest
import httpx
from datetime import datetime, timezone
from app.core.security import verify_webhook_signature, sign_webhook_payload
from app.models.webhook import WebhookSubscription, WebhookDelivery
from app.services.webhook_service import deliver_webhook_sync, queue_event


def test_webhook_signature_calculation():
    secret = "whsec_test_secret_key_12345"
    payload = {"id": "evt-1", "type": "sms.sent", "data": {"to": "+255712345678"}}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    sig = sign_webhook_payload(payload_bytes, secret)
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA-256 hex is 64 chars

    assert verify_webhook_signature(payload_bytes, secret, sig) is True
    assert verify_webhook_signature(payload_bytes, "wrong_secret", sig) is False
    assert verify_webhook_signature(b"tampered_payload", secret, sig) is False


def test_create_subscription_ssrf_protection(client, valid_api_key):
    headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}

    # SSRF target (127.0.0.1 or http or metadata IP)
    bad_payload = {
        "url": "http://127.0.0.1:8000/webhook",
        "events": ["sms.sent"],
    }
    res = client.post("/api/v1/webhooks", json=bad_payload, headers=headers)
    assert res.status_code == 400
    assert "HTTPS" in res.json()["detail"] or "forbidden" in res.json()["detail"].lower()


def test_webhook_queue_and_mock_delivery(db_session):
    # 1. Create a subscription in DB
    sub = WebhookSubscription(
        url="https://api.example.com/webhooks/sms",
        secret="whsec_my_signing_key_456",
        events=["sms.sent"],
        is_active=True,
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)

    # 2. Queue an event
    deliveries = queue_event(
        db_session,
        event_type="sms.sent",
        data={"message_id": "msg-123", "status": "sent"},
    )
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.status == "pending"

    # 3. Deliver using mock HTTP client responding 200 OK
    def mock_handler(request: httpx.Request):
        assert request.headers.get("X-Event-Type") == "sms.sent"
        assert "X-Signature-SHA256" in request.headers
        assert "X-Timestamp" in request.headers
        return httpx.Response(200, text='{"received": true}')

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    result = deliver_webhook_sync(db_session, delivery, client=mock_client)

    assert result.status == "delivered"
    assert result.response_status_code == 200
    assert result.delivered_at is not None
