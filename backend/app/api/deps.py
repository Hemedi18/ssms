import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional
from fastapi import Depends, HTTPException, Security, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import hash_secret, ensure_utc
from app.models.api_key import ApiKey
from app.models.device import GatewayDevice

security_scheme = HTTPBearer(auto_error=False)

# In-memory rate limiting bucket: key_id -> list of timestamps
_rate_limit_buckets = defaultdict(list)


def get_current_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Authenticates API client credentials and enforces rate limiting."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Use 'Bearer <YOUR_API_KEY>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials
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
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    db: Session = Depends(get_db),
) -> GatewayDevice:
    """Authenticates gateway device bearer token."""
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

    return device
