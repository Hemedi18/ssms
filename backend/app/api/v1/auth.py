from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any

from app.core.config import settings
from app.core.security import create_admin_token, verify_secret, hash_secret
from app.api.deps import get_current_admin

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(..., description="Administrator username", json_schema_extra={"example": "admin"})
    password: str = Field(..., description="Administrator password", json_schema_extra={"example": "hemy@2004"})



class UserProfile(BaseModel):
    username: str
    name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


@router.post("/login", response_model=LoginResponse)
def admin_login(payload: LoginRequest):
    """
    Authenticates the administrator and returns an HMAC-SHA256 signed session token.
    Credentials configured by administrator: admin / hemy@2004.
    """
    is_valid_user = payload.username.strip() == settings.ADMIN_USERNAME.strip()
    is_valid_pass = payload.password.strip() == settings.ADMIN_PASSWORD.strip()

    if not (is_valid_user and is_valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password. Please verify your credentials.",
        )

    token = create_admin_token(
        username=settings.ADMIN_USERNAME,
        secret_key=settings.SECRET_KEY,
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


@router.get("/me", response_model=UserProfile)
def get_current_user_profile(admin: Dict[str, Any] = Depends(get_current_admin)):
    """Validates the current session token and returns administrator profile."""
    return UserProfile(
        username=admin.get("sub", settings.ADMIN_USERNAME),
        name="System Administrator",
        role="superadmin",
    )


@router.post("/logout")
def admin_logout():
    """Client-side session invalidation endpoint."""
    return {"status": "success", "message": "Successfully logged out."}
