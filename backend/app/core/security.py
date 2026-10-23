import hmac
import hashlib
import re
import secrets
from datetime import datetime, timezone
from typing import Tuple, Optional


def hash_secret(secret: str) -> str:
    """Computes a SHA-256 hex digest of the secret."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


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
    clean = re.sub(r"[\s\-\(\)]", "", phone.strip())
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
    else:
        cc = default_country_code if default_country_code.startswith("+") else f"+{default_country_code}"
        normalized = f"{cc}{clean}"

    if not E164_REGEX.match(normalized):
        raise ValueError(
            f"Invalid E.164 phone number: '{phone}'. Must be + followed by 7-15 digits (e.g., +255712345678)."
        )
    return normalized
