import logging
import re
import sys
from typing import Any, Dict


def mask_phone_number(phone: str) -> str:
    """Masks middle digits of a phone number (e.g., '+255712345678' -> '+255***678')."""
    if not phone or len(phone) < 6:
        return phone
    return f"{phone[:4]}***{phone[-3:]}"


def sanitize_log_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redacts sensitive fields like credentials, tokens, and secrets."""
    sensitive_keys = {
        "authorization", "token", "key", "secret", "password",
        "api_key", "device_token", "pairing_code"
    }
    sanitized = {}
    for k, v in data.items():
        lower_k = k.lower()
        if any(s in lower_k for s in sensitive_keys):
            sanitized[k] = "[REDACTED]"
        elif lower_k in {"to", "from_number", "phone_number"} and isinstance(v, str):
            sanitized[k] = mask_phone_number(v)
        elif isinstance(v, dict):
            sanitized[k] = sanitize_log_dict(v)
        else:
            sanitized[k] = v
    return sanitized


class SafeFormatter(logging.Formatter):
    """Custom logging formatter that strips sensitive patterns from raw strings."""

    SENSITIVE_PATTERNS = [
        re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE),
        re.compile(r"(sms_live_[A-Za-z0-9_\-]{8,})", re.IGNORECASE),
        re.compile(r"(dev_tok_[A-Za-z0-9_\-]{8,})", re.IGNORECASE),
        re.compile(r"(whsec_[A-Fa-f0-9]{8,})", re.IGNORECASE),
    ]

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pattern in self.SENSITIVE_PATTERNS:
            msg = pattern.sub(r"\1[REDACTED]" if "(" in pattern.pattern else "[REDACTED]", msg)
        return msg


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configures application logger."""
    logger = logging.getLogger("sms_gateway")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            SafeFormatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
        )
        logger.addHandler(handler)

    return logger


logger = setup_logging()
