from datetime import datetime, timezone, timedelta
from app.models.api_key import ApiKey
from app.core.security import generate_api_key


def test_missing_auth_header(client):
    response = client.get("/api/v1/messages")
    assert response.status_code == 401
    assert "Missing or malformed Authorization" in response.json()["detail"]


def test_invalid_api_key(client):
    headers = {"Authorization": "Bearer sms_live_invalid_key_random12345"}
    response = client.get("/api/v1/messages", headers=headers)
    assert response.status_code == 401
    assert "Invalid or deactivated" in response.json()["detail"]


def test_expired_api_key(client, db_session):
    raw_key, prefix, key_hash = generate_api_key()
    expired = ApiKey(
        name="Expired Key",
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=["sms:read"],
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(expired)
    db_session.commit()

    headers = {"Authorization": f"Bearer {raw_key}"}
    response = client.get("/api/v1/messages", headers=headers)
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_forbidden_scope(client, readonly_api_key):
    # readonly_api_key only has "sms:read", but /messages POST requires "sms:send"
    headers = {"Authorization": f"Bearer {readonly_api_key['raw_key']}"}
    payload = {"to": "+255712345678", "message": "Test"}
    response = client.post("/api/v1/messages", json=payload, headers=headers)
    assert response.status_code == 403
    assert "lacks required permission scope" in response.json()["detail"]


def test_rate_limiting(client, db_session):
    raw_key, prefix, key_hash = generate_api_key()
    limited_key = ApiKey(
        name="Rate Limited Client",
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=["sms:read"],
        rate_limit=2,  # allow only 2 req/min
    )
    db_session.add(limited_key)
    db_session.commit()

    headers = {"Authorization": f"Bearer {raw_key}"}
    res1 = client.get("/api/v1/messages", headers=headers)
    assert res1.status_code == 200
    res2 = client.get("/api/v1/messages", headers=headers)
    assert res2.status_code == 200
    res3 = client.get("/api/v1/messages", headers=headers)
    assert res3.status_code == 429
    assert "Rate limit exceeded" in res3.json()["detail"]
