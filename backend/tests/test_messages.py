import pytest
from app.models.message import Message


def test_create_message_success(client, valid_api_key):
    headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}
    payload = {
        "to": "+255712345678",
        "message": "Hello from SIM SMS Gateway automated test!",
        "client_reference": "ref-001",
    }
    response = client.post("/api/v1/messages", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["to"] == "+255712345678"
    assert data["status"] == "queued"
    assert data["parts_count"] == 1
    assert data["client_reference"] == "ref-001"
    assert "id" in data


def test_multipart_message(client, valid_api_key):
    headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}
    long_text = "This is a long SMS message designed to test multipart message concatenation. " * 3
    assert len(long_text) > 160
    payload = {
        "to": "+255712345678",
        "body": long_text,
    }
    response = client.post("/api/v1/messages", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["parts_count"] >= 2


def test_invalid_phone_number(client, valid_api_key):
    headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}
    payload = {
        "to": "invalid_phone_number_abc",
        "message": "Test text",
    }
    response = client.post("/api/v1/messages", json=payload, headers=headers)
    assert response.status_code == 400
    assert "Invalid E.164" in response.json()["detail"]


def test_idempotent_duplicate_submission(client, valid_api_key):
    headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}
    payload = {
        "to": "+255712345678",
        "message": "Idempotent payment notification",
        "idempotency_key": "order-idem-9999",
    }
    # First submit -> 201 Created
    res1 = client.post("/api/v1/messages", json=payload, headers=headers)
    assert res1.status_code == 201
    msg1_id = res1.json()["id"]

    # Second submit with same idempotency key -> 200 OK, same ID
    res2 = client.post("/api/v1/messages", json=payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["id"] == msg1_id


def test_list_and_get_messages(client, valid_api_key):
    headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}
    # Create 2 messages
    client.post("/api/v1/messages", json={"to": "+255712111111", "message": "Msg 1"}, headers=headers)
    client.post("/api/v1/messages", json={"to": "+255712222222", "message": "Msg 2"}, headers=headers)

    res = client.get("/api/v1/messages", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 2

    first_id = items[0]["id"]
    res_single = client.get(f"/api/v1/messages/{first_id}", headers=headers)
    assert res_single.status_code == 200
    assert res_single.json()["id"] == first_id

    # Check events
    res_events = client.get(f"/api/v1/messages/{first_id}/events", headers=headers)
    assert res_events.status_code == 200
    events = res_events.json()
    assert len(events) >= 1
    assert events[0]["status"] == "queued"


def test_retry_message_flow(client, valid_api_key, db_session):
    headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}
    create_res = client.post(
        "/api/v1/messages",
        json={"to": "+255712999999", "message": "Will fail and retry"},
        headers=headers,
    )
    msg_id = create_res.json()["id"]

    # Trying to retry when status is still 'queued' should be rejected
    res_early_retry = client.post(f"/api/v1/messages/{msg_id}/retry", headers=headers)
    assert res_early_retry.status_code == 400

    # Mark message as failed directly in DB
    msg = db_session.get(Message, msg_id)
    msg.status = "failed"
    msg.error_message = "Radio failure"
    db_session.commit()

    # Retry should succeed now
    res_retry = client.post(f"/api/v1/messages/{msg_id}/retry", headers=headers)
    assert res_retry.status_code == 200
    assert res_retry.json()["status"] == "queued"
    assert res_retry.json()["error_message"] is None
