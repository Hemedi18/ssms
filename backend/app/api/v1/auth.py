from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_admin_token, verify_password, hash_password
from app.api.deps import get_current_admin
from app.models.tenant import User, Tenant

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(..., description="Administrator username or email", json_schema_extra={"example": "admin"})
    password: str = Field(..., description="Password", json_schema_extra={"example": "hemy@2004"})
    tenant_id: Optional[str] = None


class UserProfile(BaseModel):
    username: str
    name: str
    role: str
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticates administrator or tenant user and returns an HMAC-SHA256 session token.
    Supports both legacy Super Admin credentials (admin / hemy@2004) and multi-tenant database users.
    """
    clean_user = payload.username.strip()
    clean_pass = payload.password.strip()

    # 1. Check legacy Super Admin credentials first (Preserves 100% backward compatibility)
    if clean_user == settings.ADMIN_USERNAME.strip() and clean_pass == settings.ADMIN_PASSWORD.strip():
        token = create_admin_token(
            username=settings.ADMIN_USERNAME,
            secret_key=settings.SECRET_KEY,
            role="superadmin",
            expires_in_seconds=86400 * 7,
        )
        return LoginResponse(
            access_token=token,
            token_type="bearer",
            user=UserProfile(
                username=settings.ADMIN_USERNAME,
                name="System Administrator",
                role="superadmin",
            ),
        )

    # 2. Database User Lookup (by email or username)
    user = db.scalar(
        select(User).where(
            User.email == clean_user.lower(),
            User.is_active == True,
        )
    )

    if not user or not verify_password(clean_pass, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password. Please verify your credentials.",
        )

    tenant_name = user.tenant.name if user.tenant else None

    token = create_admin_token(
        username=user.email,
        secret_key=settings.SECRET_KEY,
        tenant_id=user.tenant_id,
        user_id=user.id,
        role=user.role,
        expires_in_seconds=86400 * 7,
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserProfile(
            username=user.email,
            name=user.full_name,
            role=user.role,
            tenant_id=user.tenant_id,
            tenant_name=tenant_name,
        ),
    )


@router.get("/me", response_model=UserProfile)
def get_current_user_profile(
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Validates the current session token and returns user profile with tenant info."""
    username = admin.get("sub", settings.ADMIN_USERNAME)
    role = admin.get("role", "super_admin")
    tenant_id = admin.get("tenant_id")
    tenant_name = None

    if tenant_id:
        t = db.get(Tenant, tenant_id)
        if t:
            tenant_name = t.name

    return UserProfile(
        username=username,
        name="System Administrator" if role == "super_admin" else username,
        role=role,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
    )


@router.post("/logout")
def logout():
    """Client-side session invalidation endpoint."""
    return {"status": "success", "message": "Successfully logged out."}
