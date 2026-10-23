from app.services.device_service import create_pairing_code


def test_device_pairing_and_reuse_prevention(client, db_session):
    # 1. Create a pairing code
    pairing = create_pairing_code(db_session, device_name="Samsung S22", expires_in_seconds=300)

    # 2. Pair device
    pair_payload = {
        "pairing_code": pairing.code,
        "device_name": "My S22 Gateway",
        "model": "SM-S901B",
        "os_version": "Android 14",
        "app_version": "1.0.0",
    }
    res = client.post("/api/v1/devices/pair", json=pair_payload)
    assert res.status_code == 200
    data = res.json()
    assert "device_id" in data
    assert "device_token" in data
    assert data["device_token"].startswith("dev_tok_")

    # 3. Attempt to reuse same pairing code -> Must fail 400
    res_reuse = client.post("/api/v1/devices/pair", json=pair_payload)
    assert res_reuse.status_code == 400
    assert "Invalid or expired" in res_reuse.json()["detail"]


def test_device_heartbeat(client, paired_device):
    token = paired_device["raw_token"]
    headers = {"Authorization": f"Bearer {token}"}
    heartbeat_payload = {
        "sim_ready": True,
        "phone_number": "+255712888888",
        "carrier_name": "Airtel TZ",
        "network_type": "5G",
        "signal_level": 4,
        "battery_level": 92,
    }
    res = client.post("/api/v1/devices/heartbeat", json=heartbeat_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["sim_ready"] is True
    assert data["carrier_name"] == "Airtel TZ"
    assert data["battery_level"] == 92
    assert data["is_online"] is True


def test_device_job_leasing_and_result_reporting(client, valid_api_key, paired_device):
    client_headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}
    dev_headers = {"Authorization": f"Bearer {paired_device['raw_token']}"}

    # 1. Submit message from external client
    msg_res = client.post(
        "/api/v1/messages",
        json={"to": "+255712555555", "message": "Job lease test"},
        headers=client_headers,
    )
    assert msg_res.status_code == 201
    msg_id = msg_res.json()["id"]

    # 2. Device polls for next job
    poll_res = client.get("/api/v1/devices/jobs/next", headers=dev_headers)
    assert poll_res.status_code == 200
    job = poll_res.json()
    assert job["job_id"] == msg_id
    assert job["to"] == "+255712555555"
    assert "lease_token" in job

    # 3. Second poll should return 204 No Content because job is leased
    poll_res2 = client.get("/api/v1/devices/jobs/next", headers=dev_headers)
    assert poll_res2.status_code == 204

    # 4. Device reports 'sent' result
    result_res = client.post(
        f"/api/v1/devices/jobs/{msg_id}/result",
        json={"status": "sent", "parts_sent": 1},
        headers=dev_headers,
    )
    assert result_res.status_code == 200
    assert result_res.json()["message_status"] == "sent"

    # 5. Device reports 'delivered' result
    result_deliv = client.post(
        f"/api/v1/devices/jobs/{msg_id}/result",
        json={"status": "delivered"},
        headers=dev_headers,
    )
    assert result_deliv.status_code == 200
    assert result_deliv.json()["message_status"] == "delivered"


def test_device_revocation(client, valid_api_key, paired_device):
    client_headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}
    dev_headers = {"Authorization": f"Bearer {paired_device['raw_token']}"}
    dev_id = paired_device["device"].id

    # Revoke device via admin/client endpoint
    del_res = client.delete(f"/api/v1/devices/{dev_id}", headers=client_headers)
    assert del_res.status_code == 200

    # Device attempts heartbeat -> 401 Unauthorized
    hb_res = client.post(
        "/api/v1/devices/heartbeat",
        json={"sim_ready": True},
        headers=dev_headers,
    )
    assert hb_res.status_code == 401
    assert "revoked" in hb_res.json()["detail"].lower()
