import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any, List


def hash_secret(secret: str) -> str:
    """Computes a SHA-256 hex digest of the secret."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """
    Computes a PBKDF2-HMAC-SHA256 password hash with a random 16-byte salt and 100,000 iterations.
    Format: 'pbkdf2:sha256:100000$<salt_hex>$<hash_hex>'
    """
    salt = secrets.token_bytes(16)
    iterations = 100000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2:sha256:{iterations}${salt.hex()}${derived.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against the stored PBKDF2-HMAC-SHA256 hash or fallback.
    """
    if not hashed_password:
        return False
    if hashed_password.startswith("pbkdf2:sha256:"):
        try:
            parts = hashed_password.split("$")
            if len(parts) != 3:
                return False
            meta, salt_hex, expected_hex = parts
            iterations = int(meta.split(":")[2])
            salt = bytes.fromhex(salt_hex)
            derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(derived.hex(), expected_hex)
        except Exception:
            return False
    # Backward compatibility with SHA-256 or plaintext in dev test fixtures
    cand_hash = hash_secret(plain_password)
    if hmac.compare_digest(cand_hash, hashed_password):
        return True
    return hmac.compare_digest(plain_password, hashed_password)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures a datetime object is offset-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def verify_secret(raw_secret: str, hashed_secret: str) -> bool:
    """Constant-time comparison between hashed raw secret and stored hash."""
    candidate_hash = hash_secret(raw_secret)
    return hmac.compare_digest(candidate_hash, hashed_secret)


def generate_api_key(prefix: str = "sms_live_") -> Tuple[str, str, str]:
    """
    Generates a secure API key.
    Returns: (raw_key, key_prefix, key_hash)
    """
    random_part = secrets.token_urlsafe(32)
    raw_key = f"{prefix}{random_part}"
    key_prefix = raw_key[:12]
    key_hash = hash_secret(raw_key)
    return raw_key, key_prefix, key_hash


def generate_device_token(prefix: str = "dev_tok_") -> Tuple[str, str]:
    """
    Generates a secure device credential token.
    Returns: (raw_token, token_hash)
    """
    random_part = secrets.token_urlsafe(32)
    raw_token = f"{prefix}{random_part}"
    token_hash = hash_secret(raw_token)
    return raw_token, token_hash


def generate_pairing_code() -> str:
    """Generates an 8-character uppercase alphanumeric pairing code (e.g. '8K3M-9XP2')."""
    chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    part1 = "".join(secrets.choice(chars) for _ in range(4))
    part2 = "".join(secrets.choice(chars) for _ in range(4))
    return f"{part1}-{part2}"


def generate_webhook_secret() -> str:
    """Generates a high-entropy secret for HMAC-SHA256 webhook signatures."""
    return f"whsec_{secrets.token_hex(24)}"


def sign_webhook_payload(payload_bytes: bytes, secret: str) -> str:
    """Signs raw bytes with HMAC-SHA256 using the subscription secret."""
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    return mac.hexdigest()


def verify_webhook_signature(payload_bytes: bytes, secret: str, signature: str) -> bool:
    """Verifies that an incoming webhook signature matches the payload HMAC-SHA256."""
    expected = sign_webhook_payload(payload_bytes, secret)
    return hmac.compare_digest(expected, signature)


def verify_device_signature(payload_bytes: bytes, secret: str, signature: str) -> bool:
    """Verifies X-Device-Signature header for hardware anti-replay verification."""
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    expected = mac.hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_client_ip(client_ip: str, allowed_ips_str: Optional[str]) -> bool:
    """
    Validates client IP against allowed_ips (comma-separated IP addresses or CIDRs).
    Returns True if allowed_ips_str is empty or if client_ip matches any allowed rule.
    """
    if not allowed_ips_str or not allowed_ips_str.strip():
        return True

    try:
        ip_obj = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        return False

    for rule in allowed_ips_str.split(","):
        rule = rule.strip()
        if not rule:
            continue
        try:
            if "/" in rule:
                if ip_obj in ipaddress.ip_network(rule, strict=False):
                    return True
            else:
                if ip_obj == ipaddress.ip_address(rule):
                    return True
        except ValueError:
            continue

    return False


E164_REGEX = re.compile(r"^\+[1-9]\d{6,14}$")


def normalize_and_validate_phone(phone: str, default_country_code: str = "+255") -> str:
    """
    Validates and normalizes phone number to strict E.164 format.
    Accepts:
      - Already E.164 (e.g., '+255712345678')
      - Local format starting with 0 (e.g., '0712345678' -> '+255712345678')
      - Without plus if matching country code (e.g. '255712345678' -> '+255712345678')
    Raises ValueError on invalid numbers.
    """
    clean = re.sub(r"[\s\-\(\)\.]", "", str(phone).strip())
    if not clean:
        raise ValueError("Phone number cannot be empty")

    if clean.startswith("+"):
        normalized = clean
    elif clean.startswith("00"):
        normalized = "+" + clean[2:]
    elif clean.startswith("0"):
        cc = default_country_code if default_country_code.startswith("+") else f"+{default_country_code}"
        normalized = f"{cc}{clean[1:]}"
    elif clean.startswith(default_country_code.lstrip("+")):
        normalized = f"+{clean}"
    elif clean.startswith("255"):
        normalized = f"+{clean}"
    else:
        cc = default_country_code if default_country_code.startswith("+") else f"+{default_country_code}"
        normalized = f"{cc}{clean}"

    if not E164_REGEX.match(normalized):
        raise ValueError(
            f"Invalid E.164 phone number: '{phone}'. Must be + followed by 7-15 digits (e.g., +255712345678)."
        )
    return normalized


def create_admin_token(
    username: str,
    secret_key: str,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    role: str = "super_admin",
    expires_in_seconds: int = 86400 * 7,
) -> str:
    """
    Creates a cryptographically signed HMAC-SHA256 session token for admin / multi-tenant authentication.
    """
    payload = {
        "sub": username,
        "exp": int(time.time()) + expires_in_seconds,
        "role": role,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "nonce": secrets.token_hex(8),
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    signature = hmac.new(secret_key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_admin_token(token: str, secret_key: str) -> Optional[Dict[str, Any]]:
    """
    Verifies the HMAC-SHA256 signature and expiration of an admin / user session token.
    Returns decoded claims dict if valid, None otherwise.
    """
    if not token or "." not in token:
        return None
    parts = token.split(".")
    if len(parts) != 2:
        return None
    payload_b64, signature = parts
    expected_sig = hmac.new(secret_key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature):
        return None

    # URL-safe base64 padding
    padding = "=" * ((4 - len(payload_b64) % 4) % 4)
    try:
        raw_json = base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8")
        claims = json.loads(raw_json)
        if claims.get("exp", 0) < time.time():
            return None
        return claims
    except Exception:
        return None
