import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from .deps import chat_history
from .schemas import SignupRequest, LoginRequest, UserResponse, AuthResponse, SignupResponse

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key-task-rag-file-summariser-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7
COOKIE_NAME = "session_token"

security = HTTPBearer(auto_error=False)

# In-Memory Rate Limiter for Login/Signup: Max 15 attempts per 60 seconds per IP
_rate_limit_lock = {}
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_ATTEMPTS = 15

def check_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Clean up old timestamps
    attempts = [t for t in _rate_limit_lock.get(client_ip, []) if now - t < _RATE_LIMIT_WINDOW]
    
    if len(attempts) >= _RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Please try again after {_RATE_LIMIT_WINDOW} seconds."
        )
    
    attempts.append(now)
    _rate_limit_lock[client_ip] = attempts

def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: dict) -> str:
    """Create a signed JWT token with expiry."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=JWT_EXPIRATION_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    FastAPI dependency to authenticate requests.
    Validates token, verifies that the user still exists in the database,
    and enforces that the user status is 'approved'.
    Disabling or deleting a user invalidates their active sessions immediately.
    """
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif COOKIE_NAME in request.cookies:
        token = request.cookies.get(COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in."
        )

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again."
        )

    user_id = payload["sub"]
    user = None
    if chat_history:
        try:
            user = chat_history.get_user_by_id(user_id)
        except Exception:
            user = None

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists. Please log in again."
        )

    # Real-time status enforcement: if disabled or not approved, reject request immediately
    user_status = user.get("status", "pending")
    if user_status != "approved":
        if user_status == "disabled":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been disabled by the administrator."
            )
        elif user_status == "rejected":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been rejected by the administrator."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is waiting for admin approval."
            )

    return {
        "id": user["id"],
        "name": user.get("name") or payload.get("name") or "User",
        "email": user.get("email") or payload.get("email") or "",
        "role": user.get("role", "user"),
        "status": user.get("status", "approved"),
        "created_at": user.get("created_at")
    }

def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency that restricts endpoints exclusively to the administrator."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Administrator access required."
        )
    return current_user

@auth_router.post("/signup", response_model=SignupResponse)
def signup(req: SignupRequest, request: Request, response: Response):
    """
    Public registration endpoint.
    - Blocks registration with ADMIN_EMAIL.
    - All signups strictly receive role 'user' and status 'pending'.
    - Client-sent role or status values are ignored.
    - Login is blocked until approved by the admin.
    """
    check_rate_limit(request)
    try:
        name = req.name.strip()
        email = req.email.strip().lower()
        password = req.password

        if not name:
            raise HTTPException(status_code=400, detail="Name is required.")
        
        email_regex = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        if not re.match(email_regex, email):
            raise HTTPException(status_code=400, detail="Please provide a valid email address.")

        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

        # Block public signup with the ADMIN_EMAIL address
        admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
        if admin_email and email == admin_email:
            raise HTTPException(status_code=400, detail="This email cannot be used.")

        # Check unique email
        existing_user = chat_history.get_user_by_email(email)
        if existing_user:
            raise HTTPException(status_code=400, detail="An account with this email already exists.")

        password_hash = hash_password(password)
        # Always sets role='user' and status='pending'
        user = chat_history.create_user(name=name, email=email, password_hash=password_hash)

        return SignupResponse(
            message="Your account is waiting for admin approval.",
            status="pending",
            email=user["email"]
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Signup failed: {str(e)}")

@auth_router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request, response: Response):
    """
    Login endpoint.
    - Verifies credentials.
    - Enforces user status: pending, rejected, and disabled accounts are blocked with descriptive messages.
    - Issues JWT token only for approved accounts.
    """
    check_rate_limit(request)
    try:
        email = req.email.strip().lower()
        password = req.password

        user = chat_history.get_user_by_email(email)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        if not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        # Status validation checks
        user_status = user.get("status", "pending")
        if user_status == "pending":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is waiting for admin approval."
            )
        elif user_status == "rejected":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been rejected by the administrator."
            )
        elif user_status == "disabled":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been disabled by the administrator."
            )
        elif user_status != "approved":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not approved to access this application."
            )

        token = create_access_token({
            "sub": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user.get("role", "user")
        })

        is_https = bool(request.url.scheme == "https")
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=JWT_EXPIRATION_DAYS * 86400,
            samesite="lax",
            secure=is_https
        )

        user_resp = UserResponse(
            id=user["id"],
            name=user["name"],
            email=user["email"],
            role=user.get("role", "user"),
            status=user.get("status", "approved"),
            created_at=user.get("created_at")
        )
        return AuthResponse(token=token, user=user_resp)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@auth_router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME)
    return {"message": "Logged out successfully"}

@auth_router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        name=current_user["name"],
        email=current_user["email"],
        role=current_user.get("role", "user"),
        status=current_user.get("status", "approved"),
        created_at=current_user.get("created_at")
    )

# ==========================================
# ADMIN USER MANAGEMENT ENDPOINTS
# ==========================================

@auth_router.get("/admin/users", response_model=List[UserResponse])
def get_all_users(current_admin: dict = Depends(require_admin)):
    """Admin endpoint to list all users with role and status."""
    users = chat_history.list_all_users()
    return [
        UserResponse(
            id=u["id"],
            name=u["name"],
            email=u["email"],
            role=u.get("role", "user"),
            status=u.get("status", "pending"),
            created_at=u.get("created_at")
        )
        for u in users
    ]

@auth_router.post("/admin/users/{user_id}/approve")
def approve_user(user_id: str, current_admin: dict = Depends(require_admin)):
    """Admin approves a user account."""
    target = chat_history.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    chat_history.update_user_status(user_id, "approved")
    return {"message": "User approved successfully", "user_id": user_id, "status": "approved"}

@auth_router.post("/admin/users/{user_id}/reject")
def reject_user(user_id: str, current_admin: dict = Depends(require_admin)):
    """Admin rejects a user account."""
    target = chat_history.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target["id"] == current_admin["id"]:
        raise HTTPException(status_code=400, detail="The administrator cannot reject their own account.")
    chat_history.update_user_status(user_id, "rejected")
    return {"message": "User rejected successfully", "user_id": user_id, "status": "rejected"}

@auth_router.post("/admin/users/{user_id}/disable")
def disable_user(user_id: str, current_admin: dict = Depends(require_admin)):
    """Admin disables an active user account."""
    target = chat_history.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target["id"] == current_admin["id"]:
        raise HTTPException(status_code=400, detail="The administrator cannot disable their own account.")
    chat_history.update_user_status(user_id, "disabled")
    return {"message": "User disabled successfully", "user_id": user_id, "status": "disabled"}

@auth_router.post("/admin/users/{user_id}/enable")
def enable_user(user_id: str, current_admin: dict = Depends(require_admin)):
    """Admin re-enables a disabled user account."""
    target = chat_history.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    chat_history.update_user_status(user_id, "approved")
    return {"message": "User re-enabled successfully", "user_id": user_id, "status": "approved"}

@auth_router.delete("/admin/users/{user_id}")
def delete_user(user_id: str, current_admin: dict = Depends(require_admin)):
    """Admin deletes a user account and purges their private chats."""
    target = chat_history.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target["id"] == current_admin["id"]:
        raise HTTPException(status_code=400, detail="The administrator cannot delete their own account.")
    chat_history.delete_user(user_id)
    return {"message": "User deleted successfully", "user_id": user_id}

class CleanupRequest(BaseModel):
    retention_days: Optional[int] = None

@auth_router.post("/run-cleanup")
def run_chat_cleanup(
    req: CleanupRequest = CleanupRequest(),
    current_user: dict = Depends(get_current_user)
):
    """
    Manually triggers chat cleanup. Purges chats older than retention_days (default from env or 30).
    """
    days = req.retention_days if req.retention_days is not None else int(os.getenv("CHAT_RETENTION_DAYS", "30"))
    purged_count = chat_history.cleanup_old_chats(retention_days=days)
    return {"status": "ok", "retention_days": days, "purged_sessions_count": purged_count}
