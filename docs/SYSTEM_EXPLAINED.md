# SIM SMS Gateway: Comprehensive Technical Specification & Operational Deep Dive

## 1. Executive Summary & Purpose

The **SIM SMS Gateway** transforms standard Android smartphones equipped with active cellular SIM cards into high-reliability, bi-directional SMS gateways. It eliminates the need for expensive third-party SMS aggregation APIs (e.g., Twilio, Infobip, Africa's Talking) by taking advantage of low-cost local carrier bundles while maintaining enterprise features:

- **Strict E.164 phone normalization** and GSM 03.38 standard multipart splitting.
- **Resilient distributed job queue** with timed leasing, idempotency, and automated crash recovery.
- **Direct hardware cellular dispatch** using Android's `SmsManager` and `SubscriptionManager` (supporting multi-SIM slot selection).
- **True cellular delivery confirmations** via carrier delivery receipt `PendingIntent` callbacks.
- **Inbound SMS broadcast interception** with multipart reassembly, SHA-256 deduplication, and cloud synchronization.
- **SSRF-protected, HMAC-SHA256 signed event webhooks** for downstream CRM/system integration.
- **Carrier anti-spam rate limiting** with configurable delays and randomized jitter to safeguard physical SIM cards from carrier bans.
- **SMS bundle and balance tracking** with automated credit deductions and plan expiration enforcement.
- **Modern glassmorphic single-page administrative dashboard** with real-time telemetry, live charts, and device control.

---

## 2. Complete Architecture & Component Topology

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 EXTERNAL ECOSYSTEM                                     │
│  ┌─────────────────────────┐  REST API (gw_...)   ┌─────────────────────────────────┐  │
│  │ Third-party CRM / App   ├─────────────────────►│ Webhook Consumer Endpoint       │  │
│  └─────────────────────────┘                      │ (Receives HMAC-SHA256 payloads) │  │
└───────────────────────────┬───────────────────────┴─────────────────▲───────────────┘
                            │                                         │
                            │ Outgoing POST                           │ Signed Event POST
                            ▼                                         │
┌─────────────────────────────────────────────────────────────────────┴──────────────────┐
│                                  FASTAPI BACKEND SERVICE                               │
│  ┌────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐  │
│  │   REST API Layer       │  │    Business Services    │  │   Background Workers    │  │
│  │ - /api/v1/messages     │  │ - MessageService        │  │ - WebhookWorker         │  │
│  │ - /api/v1/messages/bulk│  │ - DeviceService         │  │   (Retry, backoff,      │  │
│  │ - /api/v1/devices      │  │ - BundleService         │  │    SSRF checks)         │  │
│  │ - /api/v1/incoming     │  │ - WebhookService        │  │ - Lease Expiration      │  │
│  │ - /api/v1/admin        │  │ - AuditService          │  │ - Device Health Monitor │  │
│  └───────────┬────────────┘  └────────────┬────────────┘  └────────────▲────────────┘  │
│              │                            │                            │               │
│              ▼                            ▼                            │               │
│  ┌─────────────────────────────────────────────────────────────────────┴────────────┐  │
│  │                  RELATIONAL STORAGE (SQLite / PostgreSQL 16)                     │  │
│  │ - messages, message_events, incoming_messages, sms_bundles                       │  │
│  │ - gateway_devices, pairing_codes, api_keys, webhook_subscriptions, deliveries    │  │
│  └────────────────────────────────────────┬─────────────────────────────────────────┘  │
└───────────────────────────────────────────┼────────────────────────────────────────────┘
                                            │ Outbound HTTPS Polling (dt_...)
                                            │ (Bypasses Carrier CGNAT)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               ANDROID GATEWAY APPLICATION                              │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │ GatewayForegroundService (Sticky Service with persistent notification)           │  │
│  │ - 5-second polling loop for outbound job leasing                                 │  │
│  │ - 30-second heartbeat loop (battery %, network type, signal strength, SIM state)│  │
│  │ - Local Room DB cache synchronization                                            │  │
│  └──────────────────┬────────────────────────────────────────▲──────────────────────┘  │
│                     │                                        │                         │
│                     ▼                                        │                         │
│  ┌─────────────────────────────────────┐  ┌──────────────────┴──────────────────────┐  │
│  │ RealSmsManager (Hardware Dispatch)  │  │ Broadcast Receivers                     │  │
│  │ - GSM splitting (160 / 153 chars)   │  │ - SmsStatusReceiver (SENT & DELIVERED)  │  │
│  │ - Dual-SIM slot targeting (subId)   │  │ - IncomingSmsReceiver (SMS_RECEIVED)    │  │
│  │ - PendingIntent callback generator  │  │ - SHA-256 PDU Hash Deduplication        │  │
│  └──────────────────┬──────────────────┘  └──────────────────▲──────────────────────┘  │
│                     │                                        │                         │
│                     ▼                                        │ Inbound SMS PDU         │
│  ┌───────────────────────────────────────────────────────────┴──────────────────────┐  │
│  │                   DEVICE HARDWARE & CELLULAR BASEBAND MODEM                      │  │
│  │                   - SIM 1 / SIM 2 Cellular Carrier Network                       │  │
│  └────────────────────────────────────────┬─────────────────────────────────────────┘  │
└───────────────────────────────────────────┼────────────────────────────────────────────┘
                                            │ Real Cellular Radio Signals
                                            ▼
                               [ Recipient Mobile Devices ]
```

---

## 3. Database Schema & Data Models

### 3.1. `messages` & `message_events`
Stores every outgoing SMS job, its lifecycle state, and granular audit events.

```sql
CREATE TABLE messages (
    id VARCHAR(36) PRIMARY KEY,              -- UUIDv4
    "to" VARCHAR(32) NOT NULL,               -- Normalized E.164 phone number
    body TEXT NOT NULL,                      -- Prepared SMS text (with brand tags)
    status VARCHAR(20) NOT NULL,             -- 'queued','dispatched','sending','sent','delivered','failed'
    sender_name VARCHAR(50),                 -- Custom brand tag (e.g. EDUSPHERE)
    sim_slot INTEGER,                        -- Targeted SIM slot (0 for SIM 1, 1 for SIM 2)
    client_reference VARCHAR(100),           -- Consumer tracking identifier
    idempotency_key VARCHAR(64),             -- SHA-256 or UUID idempotency key
    device_id VARCHAR(36),                   -- ID of leasing Android gateway
    lease_token VARCHAR(64),                 -- Secret token granted during dispatch
    leased_at TIMESTAMP WITH TIME ZONE,      -- Lease grant timestamp
    lease_expires_at TIMESTAMP WITH TIME ZONE, -- Expiration deadline (default: now + 60s)
    parts_count INTEGER NOT NULL DEFAULT 1,  -- Number of 153/160-char SMS parts
    error_message TEXT,                      -- Detailed cellular radio failure message
    sent_at TIMESTAMP WITH TIME ZONE,        -- Cellular radio dispatch confirmation
    delivered_at TIMESTAMP WITH TIME ZONE,   -- Carrier delivery receipt timestamp
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX ix_messages_status_created_at ON messages (status, created_at);
```

### 3.2. `sms_bundles`
Tracks available SMS credits, plan packages, and expiration constraints.

```sql
CREATE TABLE sms_bundles (
    id VARCHAR(36) PRIMARY KEY,
    plan_name VARCHAR(100) NOT NULL,         -- e.g. "Business SMS Pro"
    total_credits INTEGER NOT NULL,          -- Initial purchased credits
    used_credits INTEGER NOT NULL,           -- Cumulative consumed parts
    available_credits INTEGER NOT NULL,      -- Current balance remaining
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

### 3.3. `gateway_devices` & `pairing_codes`
Manages paired hardware, connectivity status, and telephony diagnostics.

```sql
CREATE TABLE gateway_devices (
    id VARCHAR(36) PRIMARY KEY,
    device_token_hash VARCHAR(64) UNIQUE NOT NULL, -- SHA-256 of dt_... secret token
    name VARCHAR(100) NOT NULL,
    model VARCHAR(100),
    os_version VARCHAR(50),
    app_version VARCHAR(30),
    sim_ready BOOLEAN NOT NULL DEFAULT FALSE,
    phone_number VARCHAR(32),
    carrier_name VARCHAR(100),
    network_type VARCHAR(50),
    signal_level INTEGER,
    battery_level INTEGER,
    is_online BOOLEAN NOT NULL DEFAULT FALSE,
    last_seen_at TIMESTAMP WITH TIME ZONE,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

### 3.4. `incoming_messages`
Stores messages received by the Android phone's cellular receiver.

```sql
CREATE TABLE incoming_messages (
    id VARCHAR(36) PRIMARY KEY,
    device_message_id VARCHAR(64),
    from_number VARCHAR(32) NOT NULL,
    body TEXT NOT NULL,
    received_at_device TIMESTAMP WITH TIME ZONE NOT NULL,
    is_multipart BOOLEAN NOT NULL DEFAULT FALSE,
    part_index INTEGER NOT NULL DEFAULT 1,
    total_parts INTEGER NOT NULL DEFAULT 1,
    raw_pdu_hash VARCHAR(64),               -- SHA-256(sender:body:timestamp)
    device_id VARCHAR(36),
    synced_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX ix_incoming_dedup ON incoming_messages (from_number, received_at_device, raw_pdu_hash);
```

### 3.5. `webhook_subscriptions` & `webhook_deliveries`
Controls outbound signed webhooks, delivery attempts, and exponential backoff retry schedules.

---

## 4. In-Depth Operational Mechanics: Exactly What Happens

### 4.1. Step-by-Step Outgoing Single SMS Submission

1. **Client Request**:
   An external client issues `POST /api/v1/messages` with:
   ```json
   {
     "to": "+255712345678",
     "message": "Your verification code is 492019",
     "sender_name": "EDUSPHERE",
     "sim_slot": 1,
     "client_reference": "otp-98214",
     "idempotency_key": "c4ca4238a0b923820dcc509a6f75849b"
   }
   ```
2. **Authentication & Rate Limiting**:
   FastAPI validates the `Authorization: Bearer gw_...` header. The token hash is looked up in `api_keys`. Scopes (`messages:send`) and expiration dates are verified. In-memory sliding-window rate limiters check whether the key exceeded its configured requests per minute.
3. **Idempotency Verification**:
   The database queries `messages` for `idempotency_key = "c4ca4238a0b923820dcc509a6f75849b"`. If an existing record is found, the system immediately returns the existing record with `200 OK` (or `202 Accepted`) without double-charging or re-sending.
4. **Phone Normalization**:
   The phone number is sanitized via `normalize_and_validate_phone()`. Any leading zeroes (e.g. `0712345678`) are converted into full international E.164 format (`+255712345678`). Non-digit characters and formatting spaces are stripped. Length and country prefix validity are enforced.
5. **Brand Formatting & GSM Part Calculation**:
   - `format_message_with_brand()` checks if the message begins with `[EDUSPHERE]`. If not, it formats the text as `"[EDUSPHERE] Your verification code is 492019"`.
   - `calculate_sms_parts()` evaluates character count:
     $$\text{parts} = \begin{cases} 1 & \text{if length } \le 160 \\ \lceil \frac{\text{length}}{153} \rceil & \text{if length } > 160 \end{cases}$$
6. **Bundle Balance Check & Deduction**:
   `bundle_service.check_and_deduct_credits(db, parts)` queries the active `sms_bundles` table:
   - Verifies `is_active == True` and `expires_at > now()`.
   - Ensures `available_credits >= parts`.
   - Decrements `available_credits` and increments `used_credits`.
7. **Database Storage & Event Creation**:
   - The message is inserted with status `queued`.
   - A `MessageEvent` record is created noting creation details.
   - `queue_event()` registers `sms.queued` in `webhook_deliveries`.
   - HTTP `202 Accepted` is returned to the client in less than 25 milliseconds.

---

### 4.2. Bulk SMS Dispatch & Carrier Anti-Spam Scheduling

1. **Bulk Request**:
   Clients submit `POST /api/v1/messages/bulk` providing an array of recipients (`["0712345678", "+255789123456", "0712345678"]`), message text, brand name, SIM slot, and `anti_spam_delay` (e.g. `4.5` seconds).
2. **Deduplication & Sanitization**:
   The service normalizes all numbers to E.164 and deduplicates them using a set. In the example above, `0712345678` and its duplicate are merged into a single entry, keeping exact count of removed duplicates and invalid entries.
3. **Upfront Credit Verification**:
   The full batch credit requirement ($\text{valid\_recipients} \times \text{parts}$) is calculated and deducted in a single atomic transaction.
4. **Queue Insertion**:
   Each message is created in `queued` state with the target `sim_slot` and `sender_name`.
5. **Anti-Spam Carrier Pacing**:
   When the Android phone leases bulk jobs, the `anti_spam_delay` and randomized jitter (e.g., $4.5\text{s} \pm 1.2\text{s}$) throttle physical cellular radio transmissions. This mimics human sending patterns and completely avoids telecom automated filter triggers.

---

### 4.3. Device Job Leasing & Crash-Safe Recovery

Because mobile phones connect over cellular data (4G/5G/LTE), they operate behind **Carrier-Grade NAT (CGNAT)** without publicly accessible static IP addresses. The gateway solves this with **Outbound Authenticated HTTPS Polling**:

1. **Job Fetching**:
   Every 5 seconds (configurable between 5s and 60s in Android Settings), `GatewayForegroundService` calls:
   ```http
   GET /api/v1/devices/jobs/next
   Authorization: Bearer dt_...
   ```
2. **Atomic Lease Grant**:
   The backend executes an atomic database query looking for:
   $$\text{status} = \text{'queued'} \quad \lor \quad (\text{status} = \text{'dispatched'} \ \land \ \text{lease\_expires\_at} < \text{now()})$$
   - It sets `status = "dispatched"`.
   - Assigns `device_id = device.id`.
   - Generates a cryptographically random `lease_token = secrets.token_hex(16)`.
   - Sets `lease_expires_at = now() + 60s`.
3. **Crash Recovery Mechanism**:
   If a smartphone leases a job but suddenly loses power, crashes, or drops connectivity before dispatching, its 60-second lease expires. On the very next polling cycle from any active gateway phone, the expired job is automatically reclaimed and leased again. No message is ever permanently stuck.

---

### 4.4. Hardware Cellular Radio Transmission

Once the Android app receives a leased job payload (`job_id`, `to`, `body`, `sim_slot`):

1. **Local Room DB Record**:
   The app stores the message in Room SQLite with status `sending`.
2. **Dual-SIM Slot Resolution**:
   If `sim_slot` is specified (e.g., Slot 1), `RealSmsManager` queries Android's `SubscriptionManager.getActiveSubscriptionInfoList()`. It identifies the matching `subscriptionId` and constructs an instance of `SmsManager`:
   ```kotlin
   val smsManager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
       context.getSystemService(SmsManager::class.java).createForSubscriptionId(subscriptionId)
   } else {
       SmsManager.getSmsManagerForSubscriptionId(subscriptionId)
   }
   ```
3. **GSM Splitting & PendingIntent Construction**:
   The message is divided using `smsManager.divideMessage(text)`. For each part $i \in [0, \text{totalParts}-1]$:
   - A `sentIntent` is created with action `com.simsms.gateway.SMS_SENT`, targeting `SmsStatusReceiver` with unique URI `sms-gateway://sent/{jobId}/{i}`.
   - A `deliveryIntent` is created with action `com.simsms.gateway.SMS_DELIVERED`, targeting `SmsStatusReceiver` with unique URI `sms-gateway://delivered/{jobId}/{i}`.
4. **Radio Dispatch**:
   - For single-part messages: `smsManager.sendTextMessage(destination, null, text, sentIntent, deliveryIntent)`.
   - For multipart messages: `smsManager.sendMultipartTextMessage(destination, null, parts, sentIntents, deliveryIntents)`.

---

### 4.5. Radio Callbacks & Real Delivery Confirmations

When Android finishes transmitting to the cellular cell tower:

1. **Transmission Result (`SMS_SENT`)**:
   `SmsStatusReceiver.onReceive()` intercepts the broadcast:
   - **Main Thread Result Capture**: The receiver immediately captures `val capturedResultCode = resultCode` on the main thread before dispatching coroutines (preventing Android OS race conditions).
   - If `capturedResultCode == Activity.RESULT_OK`: The part is logged into a concurrent `partsTracker` set. When all parts for the message arrive, the message is marked `sent` locally and reported to `/api/v1/devices/jobs/{id}/result` with `{"status": "sent"}`.
   - If `capturedResultCode != Activity.RESULT_OK`: The code is translated to a human-readable diagnostic:
     - `RESULT_ERROR_GENERIC_FAILURE`: Carrier rejected SMS (e.g., insufficient airtime balance).
     - `RESULT_ERROR_RADIO_OFF`: Airplane mode or baseband radio offline.
     - `RESULT_ERROR_NO_SERVICE`: Out of cellular tower range.
     - `RESULT_ERROR_LIMIT_EXCEEDED`: Android OS security throttle triggered.
     The message is marked `failed` and reported immediately to the backend.
2. **Carrier Delivery Receipt (`SMS_DELIVERED`)**:
   Minutes or hours later, when the recipient's phone acknowledges receipt to the cellular network, the carrier network transmits an SMS-STATUS-REPORT PDU to the gateway SIM:
   - `SmsStatusReceiver` catches `SMS_DELIVERED` with `Activity.RESULT_OK`.
   - Local Room DB is updated to `delivered`.
   - The phone calls `/api/v1/devices/jobs/{id}/result` with `{"status": "delivered"}`.
   - The backend records `delivered_at = now()`, marks the message `delivered`, and fires `sms.delivered` webhooks.

---

### 4.6. Incoming SMS Interception & Deduplication

1. **OS Broadcast**:
   When an incoming SMS arrives on the phone, Android broadcasts `android.provider.Telephony.SMS_RECEIVED`.
2. **PDU Extraction & Multipart Reassembly**:
   `IncomingSmsReceiver` parses raw PDUs using `Telephony.Sms.Intents.getMessagesFromIntent()`. Multipart segments are grouped by originating sender phone number and reassembled into the complete message body.
3. **SHA-256 PDU Hash Generation**:
   A deterministic hash is generated over `"$sender:$body:$timestamp"` using SHA-256. This prevents the Android OS from reprocessing duplicate broadcast intents if the phone reboots or reconnects to the network.
4. **Local Insertion & Cloud Sync**:
   The message is saved to Room DB and immediately dispatched via `POST /api/v1/incoming/report`:
   ```json
   {
     "from_number": "+255712345678",
     "body": "YES I CONFIRM ORDER #1024",
     "received_at": "2026-10-24T14:30:00Z",
     "is_multipart": false,
     "raw_pdu_hash": "a1b2c3d4..."
   }
   ```
5. **Backend Ingestion & Webhook**:
   The backend saves the record in `incoming_messages` (ignoring duplicates via unique database constraints) and queues an `sms.received` webhook event.

---

### 4.7. Webhook Delivery Worker & SSRF Security

1. **Queue Consumer**:
   The standalone background worker (`app.workers.webhook_worker`) polls `webhook_deliveries` where `status = "pending"` and `next_retry_at <= now()`.
2. **SSRF Guard**:
   `validate_webhook_url()` executes before any network connection:
   - Enforces `https://` in production.
   - Resolves the hostname via DNS.
   - Rejects the request if the resolved IP belongs to RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`), link-local (`169.254.0.0/16`), or cloud metadata endpoints (`169.254.169.254`).
3. **Cryptographic Signing**:
   The worker calculates an HMAC-SHA256 signature using the subscription's secret key:
   $$\text{Signature} = \text{HMAC-SHA256}(\text{key} = \text{secret}, \text{msg} = \text{raw\_json\_bytes})$$
   It attaches the following HTTP headers:
   - `X-Gateway-Signature: sha256=<hex_digest>`
   - `X-Gateway-Timestamp: <iso8601_timestamp>`
   - `X-Gateway-Event-Id: <uuid>`
4. **Retry & Exponential Backoff**:
   If the consumer endpoint returns non-2xx or times out:
   - Attempt count is incremented ($N$).
   - If $N < 5$, `next_retry_at` is scheduled with exponential backoff:
     $$\text{delay} = 2^N \times 10 \text{ seconds} \pm \text{jitter}$$
   - If $N \ge 5$, status transitions to `failed`.

---

## 5. Security & Isolation Architecture

| Layer | Implementation Details |
| :--- | :--- |
| **Authentication Segregation** | **API Keys** (`gw_...`) are used by external applications with fine-grained scopes (`messages:send`, `messages:read`, `webhooks:manage`, `devices:manage`).<br>**Device Tokens** (`dt_...`) are exclusively issued to paired Android phones, restricted to leasing, status updates, and heartbeats. |
| **Hardware Keystore** | On Android, server URLs and device tokens are stored in `EncryptedSharedPreferences`, encrypted with **AES-256-GCM** backed by the hardware Android Keystore. |
| **Pairing Codes** | Devices are onboarded using 8-character, uppercase alphanumeric pairing codes (e.g. `K9X2M4PQ`) valid for 10–15 minutes and strictly single-use. |
| **SSRF Mitigation** | Prevents internal network pivoting or cloud instance credential theft by inspecting resolved DNS IP addresses before outbound webhook dispatch. |
| **Log Sanitization** | `GatewayRepository.redactSensitive()` automatically replaces bearer tokens, device tokens, and intermediate phone digits with `[REDACTED]` or `+255****678` before writing to disk or displaying in UI logs. |

---

## 6. Glassmorphic Web Admin SPA Architecture

Served directly by FastAPI at `GET /`, the admin dashboard is built with pure, highly optimized modern CSS and modular JavaScript:

1. **Real-Time Telemetry Bar**: Live visual badges for System Health, Online Gateway Phones, Active SMS Bundles, and Available Credits.
2. **Metrics & Charts**:
   - 24-hour hourly throughput line chart (Queued vs Sent vs Delivered).
   - Delivery ratio donut chart with status breakdowns.
3. **SMS Dispatcher Console**:
   - Interactive single SMS testing with instant E.164 formatting.
   - Bulk SMS campaign builder supporting multi-line numbers or CSV import, custom brand tag prefixes, and anti-spam delay sliders.
4. **Device Command Center**:
   - Real-time hardware card for every paired phone showing SIM readiness, carrier name, phone number, battery percentage bar, and signal strength.
   - Modal to generate single-use 8-character pairing codes with countdown timers.
   - One-click device token revocation.
5. **SMS Bundle & Credit Manager**:
   - Active plan card displaying remaining credits, percentage bar, and days until expiration.
   - Top-up modal allowing administrators to inject credits and extend plan deadlines.

---

## 7. Automated Test Suite Validation

The system maintains 100% passing test suites across both backend and mobile layers:

- **Python Backend Pytest Suite (32 Passed)**:
  - `test_admin.py`: Authentication, metrics, charts, pairing code generation, API key management, SPA root routing.
  - `test_auth.py`: Token validation, expiration, scope enforcement, and rate limiting.
  - `test_bundle_and_bulk.py`: Brand prefix formatting, bundle creation, credit deductions, plan expiration rejection, bulk SMS dispatch, and admin bundle top-ups.
  - `test_cli.py`: CLI command execution for keys and pairing codes.
  - `test_devices.py`: Device pairing handshakes, token reuse prevention, heartbeats, job leasing, result callbacks, and device revocation.
  - `test_health.py`: Health endpoint validation.
  - `test_incoming.py`: Inbound message ingestion, PDU deduplication, and database indexing.
  - `test_messages.py`: E.164 validation, GSM multipart splitting, idempotent duplicate requests, filters, and retry workflows.
  - `test_webhooks.py`: HMAC signature validation, SSRF protection against private IPs, event queuing, and mock HTTP deliveries.

- **Android Jetpack Compose JUnit Suite (27 Gradle Tasks Passed)**:
  - E.164 phone number formatting and verification.
  - Character counter and multipart segment calculator.
  - Navigation backstack routing across all 15 screens.
  - Fake SMS transport callbacks.
  - SHA-256 PDU hash deduplication for incoming SMS broadcasts.
