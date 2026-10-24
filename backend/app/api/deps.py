import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional, Dict, Any, List
from fastapi import Depends, HTTPException, Security, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    hash_secret,
    ensure_utc,
    verify_admin_token,
    verify_client_ip,
    verify_device_signature,
)
from app.models.api_key import ApiKey
from app.models.device import GatewayDevice

security_scheme = HTTPBearer(auto_error=False)

# In-memory rate limiting bucket: key_id -> list of timestamps
_rate_limit_buckets = defaultdict(list)


def get_client_ip(request: Request) -> str:
    """Extracts client IP, respecting X-Forwarded-For if available."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def get_current_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Authenticates API client credentials, enforces IP whitelisting and rate limiting. Accepts Admin tokens."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Use 'Bearer <YOUR_API_KEY>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials

    # 1. Check if token is an authenticated Admin / User Session Token
    admin_claims = verify_admin_token(raw_token, settings.SECRET_KEY)
    if admin_claims:
        admin_key = ApiKey(
            id="admin-session",
            tenant_id=admin_claims.get("tenant_id"),
            name=f"User ({admin_claims.get('sub', 'admin')})",
            key_hash="",
            key_prefix="admin",
            scopes=["admin", "sms:send", "sms:read", "device:manage", "webhook:manage"],
            is_active=True,
            rate_limit=10000,
        )
        return admin_key

    # 2. Standard API key lookup
    key_hash = hash_secret(raw_token)

    api_key = db.scalar(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True,
        )
    )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or deactivated API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check expiration
    if api_key.expires_at and ensure_utc(api_key.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Enforce IP Whitelisting (CIDR and IP checks)
    client_ip = get_client_ip(request)
    if api_key.allowed_ips and not verify_client_ip(client_ip, api_key.allowed_ips):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Client IP '{client_ip}' is not permitted by API key IP whitelist.",
        )

    # Sliding window rate limiting
    now_ts = time.time()
    window_start = now_ts - 60.0
    timestamps = [t for t in _rate_limit_buckets[api_key.id] if t > window_start]
    if len(timestamps) >= api_key.rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: maximum {api_key.rate_limit} requests per minute.",
            headers={"Retry-After": "60"},
        )
    timestamps.append(now_ts)
    _rate_limit_buckets[api_key.id] = timestamps

    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return api_key


def require_scope(required_scope: str) -> Callable:
    """Dependency factory checking that the authenticated API key possesses the required scope."""
    def _scope_checker(api_key: ApiKey = Depends(get_current_api_key)) -> ApiKey:
        if not api_key.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks required permission scope '{required_scope}'",
            )
        return api_key

    return _scope_checker


def get_current_device(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    db: Session = Depends(get_db),
) -> GatewayDevice:
    """Authenticates gateway device bearer token and validates X-Device-Signature if provided."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing device authorization token. Use 'Bearer <DEVICE_TOKEN>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials
    token_hash = hash_secret(raw_token)

    device = db.scalar(
        select(GatewayDevice).where(
            GatewayDevice.device_token_hash == token_hash,
            GatewayDevice.is_revoked == False,
        )
    )

    if not device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked device token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Hardware HMAC Anti-Replay Verification (optional header)
    device_signature = request.headers.get("x-device-signature")
    if device_signature:
        timestamp = request.headers.get("x-device-timestamp", "")
        # Validate signature over raw_token + timestamp
        candidate = f"{raw_token}:{timestamp}".encode("utf-8")
        if not verify_device_signature(candidate, raw_token, device_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid X-Device-Signature header",
            )

    return device


def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
) -> Dict[str, Any]:
    """Authenticates admin session bearer token."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing admin session token. Please login.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = verify_admin_token(credentials.credentials, settings.SECRET_KEY)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin session token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


def require_role(allowed_roles: List[str]) -> Callable:
    """Dependency checking that the authenticated user possesses one of the allowed roles."""
    def _role_checker(claims: Dict[str, Any] = Depends(get_current_admin)) -> Dict[str, Any]:
        role = claims.get("role", "tenant_viewer")
        if role not in allowed_roles and role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{role}' is unauthorized for this action. Allowed: {allowed_roles}",
            )
        return claims

    return _role_checker
