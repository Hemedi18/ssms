from datetime import datetime, timezone


def test_incoming_sms_flow(client, valid_api_key, paired_device):
    dev_headers = {"Authorization": f"Bearer {paired_device['raw_token']}"}
    client_headers = {"Authorization": f"Bearer {valid_api_key['raw_key']}"}

    payload = {
        "from_number": "+255788123456",
        "body": "Your bank OTP is 748291. Do not share.",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "device_message_id": "room-local-101",
        "is_multipart": False,
        "part_index": 1,
        "total_parts": 1,
    }

    # 1. Device reports incoming SMS -> 201 Created
    res1 = client.post("/api/v1/devices/incoming", json=payload, headers=dev_headers)
    assert res1.status_code == 201
    incoming_id = res1.json()["id"]
    assert res1.json()["from_number"] == "+255788123456"

    # 2. Duplicate broadcast reported -> 200 OK, same ID
    res2 = client.post("/api/v1/devices/incoming", json=payload, headers=dev_headers)
    assert res2.status_code == 200
    assert res2.json()["id"] == incoming_id

    # 3. External application queries incoming SMS
    list_res = client.get("/api/v1/incoming", headers=client_headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    assert items[0]["from_number"] == "+255788123456"
