# Security, Privacy & Abuse Prevention Policy

SIM SMS Gateway operates as a real-world telecommunications bridge. This document outlines the security architecture, data protection controls, and anti-abuse policies implemented across the Python backend and Android application.

---

## 1. Authentication & Privilege Separation

The system strictly enforces role-based access control (RBAC) and separates client API credentials from phone gateway credentials:

```
[ External Applications ] ---> API Keys (gw_...)   ---> /api/v1/messages, /api/v1/webhooks
[ Android Phone Gateway ] ---> Device Tokens (dt_...) ---> /api/v1/devices/jobs, /api/v1/incoming
```

- **Hashed Storage**: Raw API keys and device tokens are never stored in plaintext. The database only retains cryptographic SHA-256 digests (`api_keys.key_hash`, `gateway_devices.token_hash`).
- **Ephemerality of Pairing Codes**: Pairing codes (`ABCD9876`) expire after 15 minutes, are single-use, and are hashed using SHA-256 upon generation.
- **Granular Scopes**: API keys can be restricted to specific scopes (`messages:send`, `messages:read`, `incoming:read`, `webhooks:manage`, `devices:manage`).
- **Key Revocation**: Administrators can instantly invalidate compromised API keys or device tokens via `python -m app.cli revoke-api-key` or `/api/v1/devices/{id}/revoke`.

---

## 2. On-Device Security (Android)

- **Android Keystore Integration**: Device pairing tokens and server URLs are stored in `EncryptedSharedPreferences`, encrypted with AES-256-GCM using keys stored in the hardware-backed Android Keystore.
- **No Inbound Open Ports**: The phone never listens for incoming TCP/HTTP sockets. It communicates solely via outbound authenticated polling over TLS.
- **PDU Hash Deduplication**: Incoming SMS broadcasts are processed idempotently using a SHA-256 hash over the sender, message body, and quantized timestamp, preventing replay or double-ingestion.

---

## 3. Network & Transport Security

- **Enforced TLS / HTTPS**: Remote deployments must terminate TLS via a reverse proxy (Caddy, Nginx, or Traefik). Plaintext HTTP is restricted to local development (`localhost` or `10.0.2.2`).
- **SSRF Prevention**: All webhook destination URLs are validated before registration. Requests targeting private networks (RFC 1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopbacks (`127.0.0.0/8`), link-local addresses, and cloud metadata services (`169.254.169.254`) are strictly blocked.
- **HMAC Signatures**: Every outgoing webhook request includes an HMAC-SHA256 signature in `X-Gateway-Signature` over the raw payload body.

---

## 4. Privacy, Redaction & Audit Logging

- **Log Sanitization**: The backend's `SafeFormatter` and Android's logging repository automatically redact bearer tokens, passwords, and secrets.
- **Phone Number Masking**: Phone numbers in routine diagnostic logs are masked (e.g. `+255***678`) to protect customer personal identifiable information (PII).
- **Audit Trails**: Security-critical operations (API key creation, device pairing, revocation, allowlist rejections) generate immutable entries in the `audit_events` database table.

---

## 5. Abuse Prevention & Carrier Compliance

- **E.164 Strict Validation**: Destination numbers must adhere to the international E.164 format (`^\+[1-9]\d{1,14}$`).
- **Optional Allowlist**: In testing or controlled environments, `ALLOWLIST_DESTINATIONS` can be configured in `.env` to restrict outbound SMS to pre-approved numbers only.
- **Rate Limiting**: Configurable maximum send rate (default: 60 messages/minute) protects against runaway scripts and carrier spam-filter blacklisting.
- **No Spam or Interception**: The platform does not support sender ID spoofing, unsolicited marketing broadcasts, or OTP interception. Users are strictly responsible for complying with local telecommunications regulations (e.g. TCRA, FCC, GDPR, TCPA) and obtaining explicit recipient consent.
