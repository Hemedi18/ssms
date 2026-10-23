# REST API Specification (v1)

Base URL: `http://localhost:8000/api/v1` (Production: `https://sms.yourdomain.com/api/v1`)

## 1. Authentication

The API uses standard HTTP Bearer token authentication in the `Authorization` header:

```http
Authorization: Bearer <TOKEN>
```

Two distinct token types are used:
1. **API Keys** (`gw_...`): Provisioned for external applications, web servers, and administrators. Supports granular scopes (`messages:send`, `messages:read`, `incoming:read`, `webhooks:manage`, `devices:manage`).
2. **Device Tokens** (`dt_...`): Provisioned securely during pairing for Android Gateway smartphones. Restricted to job polling, status reporting, incoming message ingestion, and heartbeats.

---

## 2. Health & Documentation

### Health Check
```http
GET /health
```
**Response (200 OK):**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2026-10-24T02:00:00Z"
}
```

### OpenAPI Documentation
- Interactive Swagger UI: `GET /docs`
- ReDoc UI: `GET /redoc`
- OpenAPI JSON Schema: `GET /openapi.json`

---

## 3. Outgoing SMS Messages

### Submit a Message
```http
POST /api/v1/messages
Authorization: Bearer <API_KEY>
Content-Type: application/json
```
```json
{
  "to": "+255712345678",
  "message": "Hello from SIM SMS Gateway! Your verification code is 849201.",
  "client_reference": "order-10025",
  "webhook_url": null
}
```
**Response (202 Accepted):**
```json
{
  "id": "e2a1b9f4-3d44-482f-870d-f5e975a6c3f1",
  "status": "queued",
  "to": "+255712345678",
  "message": "Hello from SIM SMS Gateway! Your verification code is 849201.",
  "parts_count": 1,
  "client_reference": "order-10025",
  "created_at": "2026-10-24T02:01:00Z",
  "sent_at": null,
  "delivered_at": null,
  "device_id": null
}
```

### List Messages
```http
GET /api/v1/messages?status=sent&limit=20&offset=0
Authorization: Bearer <API_KEY>
```
**Response (200 OK):**
```json
[
  {
    "id": "e2a1b9f4-3d44-482f-870d-f5e975a6c3f1",
    "status": "sent",
    "to": "+255712345678",
    "message": "Hello from SIM SMS Gateway!",
    "parts_count": 1,
    "client_reference": "order-10025",
    "created_at": "2026-10-24T02:01:00Z",
    "sent_at": "2026-10-24T02:01:05Z",
    "delivered_at": null,
    "device_id": "phone-uuid-1"
  }
]
```

### Get Message Details
```http
GET /api/v1/messages/{message_id}
Authorization: Bearer <API_KEY>
```

### Get Message Status History (Audit Events)
```http
GET /api/v1/messages/{message_id}/events
Authorization: Bearer <API_KEY>
```
**Response (200 OK):**
```json
[
  {
    "id": "evt-uuid-1",
    "message_id": "e2a1b9f4-3d44-482f-870d-f5e975a6c3f1",
    "status": "queued",
    "details": "Message accepted and queued for device dispatch",
    "timestamp": "2026-10-24T02:01:00Z"
  },
  {
    "id": "evt-uuid-2",
    "message_id": "e2a1b9f4-3d44-482f-870d-f5e975a6c3f1",
    "status": "dispatched",
    "details": "Leased to Android device OfficePhone (lease expires in 60s)",
    "timestamp": "2026-10-24T02:01:02Z"
  },
  {
    "id": "evt-uuid-3",
    "message_id": "e2a1b9f4-3d44-482f-870d-f5e975a6c3f1",
    "status": "sent",
    "details": "Cellular radio transmitted SMS successfully",
    "timestamp": "2026-10-24T02:01:05Z"
  }
]
```

### Retry a Failed Message
```http
POST /api/v1/messages/{message_id}/retry
Authorization: Bearer <API_KEY>
```
*Note: Retries are strictly permitted only for messages with status `failed`.*

---

## 4. Device Gateway Endpoints

### Pair a Device
```http
POST /api/v1/devices/pair
Content-Type: application/json
```
```json
{
  "pairing_code": "ABCD9876",
  "device_name": "Pixel 7 Gateway",
  "phone_number": "+255712345678",
  "carrier_name": "Vodacom"
}
```
**Response (200 OK):**
```json
{
  "device_id": "dev-uuid-101",
  "device_token": "dt_982bf72198cfae...",
  "device_name": "Pixel 7 Gateway",
  "status": "paired"
}
```

### Send Device Heartbeat
```http
POST /api/v1/devices/heartbeat
Authorization: Bearer <DEVICE_TOKEN>
Content-Type: application/json
```
```json
{
  "battery_level": 94,
  "signal_level": 4,
  "network_type": "LTE",
  "sim_status": "READY"
}
```

### Retrieve Next Pending Job
```http
GET /api/v1/devices/jobs/next
Authorization: Bearer <DEVICE_TOKEN>
```
**Response when job is available (200 OK):**
```json
{
  "id": "e2a1b9f4-3d44-482f-870d-f5e975a6c3f1",
  "to": "+255712345678",
  "message": "Hello from SIM SMS Gateway!",
  "lease_token": "lease_8f0a21...",
  "lease_expires_at": "2026-10-24T02:02:02Z"
}
```
*Response when no jobs are queued: `204 No Content`.*

### Report Job Result
```http
POST /api/v1/devices/jobs/{message_id}/result
Authorization: Bearer <DEVICE_TOKEN>
Content-Type: application/json
```
```json
{
  "lease_token": "lease_8f0a21...",
  "status": "sent",
  "error_message": null,
  "parts_sent": 1
}
```

---

## 5. Incoming SMS

### Report Received SMS (From Phone)
```http
POST /api/v1/incoming/report
Authorization: Bearer <DEVICE_TOKEN>
Content-Type: application/json
```
```json
{
  "sender": "+255788990011",
  "body": "YES, confirm delivery.",
  "received_at": "2026-10-24T02:05:00Z",
  "pdu_hash": "a1b2c3d4e5f6..."
}
```

### Query Incoming Messages (For Applications)
```http
GET /api/v1/incoming?sender=%2B255788990011&limit=50
Authorization: Bearer <API_KEY>
```

---

## 6. Webhooks

### Create a Webhook Subscription
```http
POST /api/v1/webhooks
Authorization: Bearer <API_KEY>
Content-Type: application/json
```
```json
{
  "url": "https://yourapp.com/webhooks/sms",
  "event_types": ["sms.queued", "sms.sent", "sms.delivered", "sms.failed", "sms.received"],
  "signing_secret": null
}
```
**Response (201 Created):**
```json
{
  "id": "sub-uuid-501",
  "url": "https://yourapp.com/webhooks/sms",
  "event_types": ["sms.queued", "sms.sent", "sms.delivered", "sms.failed", "sms.received"],
  "signing_secret": "whsec_38f90a2be...",
  "is_active": true,
  "created_at": "2026-10-24T02:10:00Z",
  "last_delivery_at": null
}
```

### List Webhook Deliveries
```http
GET /api/v1/webhooks/{subscription_id}/deliveries?limit=20
Authorization: Bearer <API_KEY>
```
