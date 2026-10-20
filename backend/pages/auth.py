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
from .schemas import SignupRequest, LoginRequest, UserResponse, AuthResponse

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
    Checks Authorization header first, then session_token cookie.
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
    user = chat_history.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists."
        )

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "created_at": user.get("created_at")
    }

@auth_router.post("/signup", response_model=AuthResponse)
def signup(req: SignupRequest, request: Request, response: Response):
    check_rate_limit(request)

    # Validations
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

    # Check unique email
    existing_user = chat_history.get_user_by_email(email)
    if existing_user:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    password_hash = hash_password(password)
    user = chat_history.create_user(name=name, email=email, password_hash=password_hash)

    # Auto-create initial default "All files" chat session for the new user
    try:
        chat_history.create_session(
            session_id=None,
            doc_id="all",
            title="All files",
            user_id=user["id"]
        )
    except Exception as e:
        print(f"[Auth] Notice creating initial session: {e}")

    # Generate token
    token = create_access_token({
        "sub": user["id"],
        "name": user["name"],
        "email": user["email"]
    })

    # Set secure httpOnly cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=JWT_EXPIRATION_DAYS * 86400,
        samesite="lax",
        secure=False  # Set to True if in HTTPS production
    )

    user_resp = UserResponse(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        created_at=user.get("created_at")
    )
    return AuthResponse(token=token, user=user_resp)

@auth_router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request, response: Response):
    check_rate_limit(request)

    email = req.email.strip().lower()
    password = req.password

    user = chat_history.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token({
        "sub": user["id"],
        "name": user["name"],
        "email": user["email"]
    })

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=JWT_EXPIRATION_DAYS * 86400,
        samesite="lax",
        secure=False
    )

    user_resp = UserResponse(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        created_at=user.get("created_at")
    )
    return AuthResponse(token=token, user=user_resp)

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
        created_at=current_user.get("created_at")
    )

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
