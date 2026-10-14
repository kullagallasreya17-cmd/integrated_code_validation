import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionFactory, get_session
from app.models import AuthSessionRecord, ProjectRecord, UserRecord
from app.security import SESSION_COOKIE, create_session_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["authentication"])
password_hasher = PasswordHasher()


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name is required")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized


def _user_payload(user: UserRecord) -> dict:
    return {
        "id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "active": user.is_active,
    }


async def _issue_session(
    user: UserRecord,
    response: Response,
    session: AsyncSession,
    remember: bool,
) -> dict:
    now = datetime.now(timezone.utc)
    await session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.expires_at <= now))
    duration = timedelta(days=settings.auth_remember_days) if remember else timedelta(hours=settings.auth_session_hours)
    token, token_hash = create_session_token()
    session.add(AuthSessionRecord(
        session_id=str(uuid4()),
        user_id=user.user_id,
        token_hash=token_hash,
        expires_at=now + duration,
    ))
    await session.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(duration.total_seconds()) if remember else None,
        expires=now + duration if remember else None,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"user": _user_payload(user)}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    existing = await session.scalar(select(UserRecord.user_id).where(UserRecord.email == request.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists")

    user = UserRecord(
        user_id=str(uuid4()),
        email=request.email,
        full_name=request.full_name,
        password_hash=password_hasher.hash(request.password),
        role="Developer",
        is_active=True,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists") from exc
    return await _issue_session(user, response, session, remember=False)


@router.post("/login")
async def login(request: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    user = await session.scalar(select(UserRecord).where(UserRecord.email == request.email))
    valid = False
    if user is not None and user.is_active:
        try:
            valid = password_hasher.verify(user.password_hash, request.password)
        except VerificationError:
            valid = False
    if not valid or user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(request.password)
    return await _issue_session(user, response, session, request.remember)


@router.post("/demo")
async def local_demo(response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    if not settings.local_demo_auth_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local demo authentication is disabled")
    user = await session.scalar(select(UserRecord).where(UserRecord.email == "demo@local.invalid"))
    if user is None:
        user = UserRecord(
            user_id=str(uuid4()),
            email="demo@local.invalid",
            full_name="Local Demo",
            password_hash=password_hasher.hash(str(uuid4())),
            role="Developer",
            is_active=True,
        )
        session.add(user)
        await session.commit()
    return await _issue_session(user, response, session, remember=False)


async def ensure_bootstrap_admin() -> None:
    if not settings.bootstrap_admin_email and not settings.bootstrap_admin_password:
        return
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        raise RuntimeError("Both GATEWAY_BOOTSTRAP_ADMIN_EMAIL and GATEWAY_BOOTSTRAP_ADMIN_PASSWORD must be set")
    if len(settings.bootstrap_admin_password) < 12:
        raise RuntimeError("The bootstrap administrator password must contain at least 12 characters")

    email = settings.bootstrap_admin_email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise RuntimeError("GATEWAY_BOOTSTRAP_ADMIN_EMAIL must be a valid email address")

    async with SessionFactory() as session:
        user = await session.scalar(select(UserRecord).where(UserRecord.email == email))
        if user is None:
            session.add(UserRecord(
                user_id=str(uuid4()),
                email=email,
                full_name=settings.bootstrap_admin_name.strip() or "System Administrator",
                password_hash=password_hasher.hash(settings.bootstrap_admin_password),
                role="Administrator",
                is_active=True,
            ))
            await session.commit()


@router.get("/me")
async def current_user(user: UserRecord = Depends(get_current_user)) -> dict:
    return {"user": _user_payload(user)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: AsyncSession = Depends(get_session),
) -> None:
    if token:
        from app.security import _token_digest

        await session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.token_hash == _token_digest(token)))
        await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=settings.auth_cookie_secure, samesite="lax")
