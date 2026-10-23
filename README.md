# SIM SMS Gateway

Turn an Android smartphone with a working SIM card into a production-grade cellular SMS gateway. External applications, websites, and business systems submit messages to a Python REST API; the Android device leases queued jobs and dispatches real SMS messages through its cellular SIM card. Real-time delivery reports and incoming SMS messages are synchronized back to the server, triggering signed HMAC-SHA256 webhooks.

---

## Architecture Overview

```
 ┌──────────────────────┐        POST /api/v1/messages         ┌───────────────────────────┐
 │ External Client / CRM├─────────────────────────────────────►│  FastAPI Backend (:8000) │
 └──────────────────────┘                                      │  - SQLite / PostgreSQL    │
                                                               │  - Job Queue with Leases  │
 ┌──────────────────────┐        Outbound HTTPS Polling        │  - Webhook Delivery Worker│
 │ Android SMS Gateway  │◄─────────────────────────────────────┤  - HMAC-SHA256 Signatures │
 │ - Jetpack Compose UI │        (Heartbeat / Job Lease)       └─────────────┬─────────────┘
 │ - Room DB & Keystore │                                                    │
 │ - SmsManager API     ├──────────────────┐                                 │
 └──────────┬───────────┘                  │                                 │
            │ Real SMS Dispatch            │ Real-time Delivery Reports      │ Signed Event Webhook
            ▼                              ▼                                 ▼
   [ Cellular Carrier ]          [ Cellular Delivery Ack ]         ┌───────────────────┐
            │                              │                       │ Client Webhook URL│
            ▼                              │                       └───────────────────┘
   [ Recipient Mobile ] ───────────────────┘
```

---

## Technology Stack

- **Android Mobile App (`android-app/`)**:
  - Kotlin & Jetpack Compose (Material 3, Dark Navy & Clean Light design system)
  - Navigation Compose (15 complete screens with working backstack and bottom nav)
  - Room SQLite local database (messages, incoming messages, app logs)
  - Android Keystore backed `EncryptedSharedPreferences`
  - Android `SmsManager` (single-part and multipart SMS with `PendingIntent` callbacks)
  - Android `Telephony.SMS_RECEIVED` broadcast receiver with SHA-256 deduplication
  - Sticky `GatewayForegroundService` for continuous polling behind mobile carrier NAT
  - Retrofit 2 & OkHttp 4 for authenticated API integration

- **Python Backend (`backend/`)**:
  - Python 3.12+ & FastAPI
  - SQLAlchemy 2.0 ORM with Alembic database migrations
  - SQLite (zero-config local dev) / PostgreSQL (production)
  - Pydantic v2 schemas and strict E.164 phone number validation
  - Persistent database queue with job lease tokens, timeout expirations, and dead-letter safety
  - SSRF-protected Webhook dispatcher with HMAC-SHA256 signatures (`X-Gateway-Signature`)
  - CLI management tool (`python -m app.cli`) for API keys, pairing codes, devices, and messages
  - 100% passing Pytest suite (`21 passed`)

---

## 15 Implemented Android Screens

All 15 screens are fully implemented with real data, navigation, and theme consistency:

1. **Splash Screen**: Logo, branding, startup initialization, and routing based on pairing state.
2. **Welcome & Onboarding**: Technical architecture overview and "Get Started" tutorial.
3. **Connect to Server**: Server URL validation, 8-character pairing code input, and device registration.
4. **Dashboard / Home**: Live operational status, connection badge, SIM readiness, stats counters, recent activity.
5. **Send SMS**: E.164 phone selector, default `+255` country code, character counter, multipart indicator, confirmation dialog.
6. **Sent Messages**: Searchable list of outgoing SMS with timestamps, parts count, and status filters.
7. **Received Messages**: Intercepted incoming SMS broadcasts with read/unread indicators and backend sync status.
8. **Inbox & Delivery Status**: Tabbed status views (All, Delivered, Pending, Failed) with color-coded badges.
9. **Message Details**: Full message body, UUIDs, timestamps, delivery events, and safe retry for failed messages.
10. **Settings**: Toggles for Foreground Service, Auto-Sync, Notifications, and Polling interval (5s - 60s).
11. **Server Configuration**: Server URL editing, connection test, device pairing status, and credential purge.
12. **SIM & Phone Information**: Real SIM status, carrier name, phone number, battery %, and permission audits.
13. **App Logs**: Diagnostic event viewer with category filters (Sent, Received, System, Connection, Error) and sensitive data redaction.
14. **Help & Setup Guide**: Step-by-step 10-point tutorial covering backend start, pairing, permissions, and troubleshooting.
15. **About**: App version 1.0.0, build metadata, connection badge, privacy policy, and carrier compliance terms.

---

## Quickstart Guide

### 1. Start the Python Backend

```bash
cd backend

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Run database migrations
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation will be available at `http://localhost:8000/docs`.

### 2. Generate Credentials via Backend CLI

```bash
cd backend
source .venv/bin/activate

# Create an API Key for external client applications
python -m app.cli create-api-key --name "WebStoreCRM" --scopes "messages:send,messages:read,incoming:read,webhooks:manage"

# Create a temporary single-use Pairing Code for your phone
python -m app.cli create-pairing-code --name "OfficePixel" --phone "+255712345678" --carrier "Vodacom"
```
The CLI will output an 8-character pairing code (e.g. `K9X2M4PQ`) valid for 15 minutes.

### 3. Build & Run the Android App

```bash
cd android-app

# Build debug APK
./gradlew assembleDebug

# Run unit tests
./gradlew testDebugUnitTest

# Install to connected device or running emulator
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### 4. Pair Your Android Phone

1. Launch **SMS Gateway** on the phone.
2. In the **Connect to Server** screen, enter:
   - **Server URL**: `http://10.0.2.2:8000` (for emulator) or `http://<your-lan-ip>:8000` (for physical phone on Wi-Fi).
   - **Pairing Code**: The 8-character code generated in Step 2.
3. Tap **Connect & Register Device**.
4. Grant the required `SEND_SMS` and `RECEIVE_SMS` Android permissions.
5. The phone is now active and polling for outgoing SMS jobs.

---

## Sending a Test Message & Verifying Webhooks

### 1. Register a Webhook Endpoint

```bash
curl -X POST http://localhost:8000/api/v1/webhooks \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://webhook.site/your-unique-uuid",
    "event_types": ["sms.queued", "sms.sent", "sms.delivered", "sms.received"]
  }'
```

### 2. Submit an Outgoing SMS

```bash
curl -X POST http://localhost:8000/api/v1/messages \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "+255712345678",
    "message": "Hello! Your verification code is 492019.",
    "client_reference": "user-reg-42"
  }'
```

The response returns HTTP 202 Accepted with status `queued`:
```json
{
  "id": "7fa8e1b3-4f92-4299-b1d6-88e367891234",
  "status": "queued",
  "to": "+255712345678",
  "created_at": "2026-10-24T02:00:00Z"
}
```

The Android phone automatically leases this job on its next polling cycle, invokes `SmsManager`, and reports the result back to the server. Your webhook endpoint receives HMAC-SHA256 signed `sms.sent` and `sms.delivered` events.

---

## Running the Automated Test Suites

### Backend Tests (Pytest)
```bash
cd backend
source .venv/bin/activate
pytest -v
```
Output: **21 passed, 0 failed** (covers health, auth, message validation, device pairing, job leasing, incoming SMS ingestion, SSRF webhook protection, HMAC signatures, and CLI commands).

### Android Tests (JUnit)
```bash
cd android-app
./gradlew testDebugUnitTest
```
Tests phone number validation, E.164 rules, multipart estimation, navigation routing for all 15 screens, fake SMS transport callbacks, and SHA-256 PDU deduplication.

---

## Physical Phone vs. Emulator Reality

| Feature | Android Emulator | Physical Android Phone |
| :--- | :--- | :--- |
| UI & 15 Screens Navigation | Fully Functional | Fully Functional |
| Room DB Persistence | Fully Functional | Fully Functional |
| Device Pairing & Token Storage | Fully Functional | Fully Functional |
| Server Polling & Heartbeats | Fully Functional | Fully Functional |
| Incoming SMS Simulation (via adb) | Fully Functional | Fully Functional |
| Real Cellular Radio SMS Transmission | **Simulated / Fails (No Cellular Tower)** | **Fully Functional (Real SIM & Towers)** |
| Carrier Delivery Reports | **Not Available** | **Available (Carrier dependent)** |

---

## Standalone Android Emulator Fix Details

If your standalone Android Emulator desktop app fails to start (`haiwaki kabisa`), this was caused by:
1. The launcher `/home/hacker/.local/bin/android-emulator-launch` referenced `/usr/lib/android-sdk`, which only had Debian ADB tools and lacked the official Google Android `emulator` binary.
2. The user account lacked write permissions in `/usr/lib/android-sdk`.
3. The system image `system-images/android-30/google_apis/x86_64` required by the `Flutter_API_30` AVD was missing.

**The Fix Implemented:**
- Installed official Google `emulator` (v37.2.12.0) and `platform-tools` (v37.0.1) into `/home/hacker/Android/Sdk`.
- Installed the full `system-images/android-30/google_apis/x86_64` package into `/home/hacker/Android/Sdk/system-images/android-30/google_apis/x86_64`.
- Updated `/home/hacker/.local/bin/android-emulator-launch` to export `ANDROID_HOME=/home/hacker/Android/Sdk` and directly execute `"$ANDROID_HOME/emulator/emulator"`.
- The desktop app "Android Emulator" now launches the emulator cleanly. You can also run it directly via:
  ```bash
  /home/hacker/Android/Sdk/emulator/emulator -avd Flutter_API_30 -gpu swiftshader_indirect
  ```
