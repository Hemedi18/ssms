from fastapi.testclient import TestClient


def test_admin_login_success(client: TestClient):
    """Verifies that the administrator can authenticate with credentials admin / hemy@2004."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "superadmin"


def test_admin_login_invalid_password(client: TestClient):
    """Verifies that bad credentials are rejected."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong_password_123"},
    )
    assert response.status_code == 401


def test_admin_stats_and_charts(client: TestClient):
    """Verifies that admin stats endpoint returns telemetry metrics and chart data."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/admin/stats", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert "summary" in data
    assert "total_messages" in data["summary"]
    assert "queued" in data["summary"]
    assert "delivered" in data["summary"]
    assert "devices" in data["summary"]
    assert "charts" in data
    assert "timeseries" in data["charts"]
    assert "status_donut" in data["charts"]


def test_admin_generate_pairing_code(client: TestClient):
    """Verifies pairing code generation from admin portal."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/admin/devices/pairing-code",
        json={"device_name": "Test Pixel 8", "expires_in_seconds": 600},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert len(data["code"]) == 9  # e.g. XXXX-XXXX


def test_admin_api_key_management(client: TestClient):
    """Verifies API key creation and revocation via admin portal."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    create_res = client.post(
        "/api/v1/admin/api-keys",
        json={"name": "Test Portal Key", "scopes": ["sms:send", "sms:read"], "rate_limit": 100},
        headers=headers,
    )
    assert create_res.status_code == 201
    key_data = create_res.json()
    assert "raw_key" in key_data
    assert key_data["name"] == "Test Portal Key"

    # List
    list_res = client.get("/api/v1/admin/api-keys", headers=headers)
    assert list_res.status_code == 200
    keys = list_res.json()
    assert any(k["id"] == key_data["id"] for k in keys)

    # Revoke
    del_res = client.delete(f"/api/v1/admin/api-keys/{key_data['id']}", headers=headers)
    assert del_res.status_code == 200


def test_spa_root_serves_html(client: TestClient):
    """Verifies that visiting / serves the SPA index.html."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "SIM SMS Gateway" in response.text
