# Webhook System Documentation

SIM SMS Gateway includes an enterprise-grade outbound webhook delivery system. When message states change or devices transition online/offline, the backend dispatches signed HTTP POST requests to configured subscriber endpoints.

---

## 1. Supported Event Types

| Event Type | Trigger Condition |
| :--- | :--- |
| `sms.queued` | A message request has been accepted, validated, and stored in the database. |
| `sms.sent` | The Android smartphone has transmitted the SMS via `SmsManager` and received a positive cellular radio acknowledgment. |
| `sms.delivered` | The cellular network has returned a genuine SMS delivery receipt callback to the phone. |
| `sms.failed` | The SMS could not be sent (e.g. no carrier signal, invalid destination, SIM credit exhausted, or repeated radio failure). |
| `sms.received` | The phone received an incoming SMS broadcast and successfully synchronized it to the backend. |
| `device.online` | A gateway phone has sent a heartbeat or polled for jobs after being offline. |
| `device.offline` | A gateway phone has missed consecutive heartbeats (idle > 90 seconds). |

---

## 2. Event Payload Schema

Every webhook delivery uses a standardized JSON envelope:

```json
{
  "id": "e81d432e-b4a0-4b3f-912b-3e5f7a1c9012",
  "type": "sms.sent",
  "created_at": "2026-10-24T02:15:30Z",
  "data": {
    "message_id": "7fa8e1b3-4f92-4299-b1d6-88e367891234",
    "to": "+255712345678",
    "status": "sent",
    "client_reference": "order-10025",
    "parts_count": 1,
    "device_id": "dev-uuid-101",
    "timestamp": "2026-10-24T02:15:28Z"
  }
}
```

---

## 3. Webhook Security & Signatures

To ensure webhook authenticity and prevent tampering, every request includes cryptographic signature headers:

- `X-Gateway-Signature`: Hex-encoded HMAC-SHA256 signature in the format `sha256=<hex_digest>`.
- `X-Gateway-Timestamp`: Unix epoch timestamp (seconds) when the request was dispatched.
- `X-Gateway-Event-Id`: Unique UUID of the webhook delivery attempt.

### Cryptographic Computation
The signature is computed over the **exact raw UTF-8 HTTP request body** using the subscription's secret key:

$$\text{Signature} = \text{HMAC-SHA256}(\text{key} = \text{signing\_secret}, \text{msg} = \text{raw\_body})$$

---

## 4. Signature Verification Examples

### Python (FastAPI / Flask)
```python
import hmac
import hashlib
from fastapi import FastAPI, Request, HTTPException, Header

app = FastAPI()
WEBHOOK_SECRET = "whsec_your_secret_here"

@app.post("/webhooks/sms")
async def handle_sms_webhook(
    request: Request,
    x_gateway_signature: str = Header(None),
    x_gateway_timestamp: str = Header(None)
):
    if not x_gateway_signature:
        raise HTTPException(status_code=401, detail="Missing signature header")

    # Read raw body bytes
    raw_body = await request.body()

    # Compute expected signature
    expected_sig = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(expected_sig, x_gateway_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    print(f"Received verified event: {payload['type']} for message {payload['data'].get('message_id')}")
    return {"status": "ok"}
```

### Node.js (Express)
```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
const WEBHOOK_SECRET = 'whsec_your_secret_here';

// Use express.raw to preserve raw buffer for signature verification
app.post('/webhooks/sms', express.raw({ type: 'application/json' }), (req, res) => {
    const signature = req.headers['x-gateway-signature'];
    if (!signature) {
        return res.status(401).send('Missing signature header');
    }

    const expectedSig = 'sha256=' + crypto
        .createHmac('sha256', WEBHOOK_SECRET)
        .update(req.body)
        .digest('hex');

    const isValid = crypto.timingSafeEqual(
        Buffer.from(signature),
        Buffer.from(expectedSig)
    );

    if (!isValid) {
        return res.status(403).send('Invalid signature');
    }

    const event = JSON.parse(req.body.toString('utf8'));
    console.log(`Verified webhook ${event.type}:`, event.data);
    res.status(200).json({ status: 'ok' });
});
```

---

## 5. Reliability & Retry Architecture

Webhook delivery is managed by a persistent database-backed worker queue:
- **Persistent Storage**: Delivery attempts are recorded in `webhook_deliveries` with HTTP status code, response body, latency, and error logs.
- **Exponential Backoff**: If the destination server returns a 5xx error or times out, the delivery is retried up to **5 times** with exponential backoff:
  - Attempt 1: Immediate
  - Attempt 2: $\approx 10$ seconds
  - Attempt 3: $\approx 30$ seconds
  - Attempt 4: $\approx 90$ seconds
  - Attempt 5: $\approx 270$ seconds
- **Idempotency**: Webhook consumers should use `payload.id` or `payload.data.message_id` to handle potential duplicate deliveries gracefully.
- **SSRF Prevention**: All webhook URLs are validated before registration. Requests targeting private networks (`10.0.0.0/8`, `192.168.0.0/16`, `172.16.0.0/12`), loopbacks (`127.0.0.0/8`), link-local, and cloud metadata services (`169.254.169.254`) are rejected with `400 Bad Request`.
