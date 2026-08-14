from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.models import UserAccount
from app.services.auth import (
    AuthenticationError,
    SessionPrincipal,
    auth_signing_secret,
    issue_session_token,
    verify_password,
    verify_session_token,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_ATTEMPT_WINDOW_SECONDS = 300
_MAX_ATTEMPTS = 5
_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempt_lock = threading.Lock()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class CurrentUserResponse(BaseModel):
    username: str
    display_name: str | None
    role: str
    is_superadmin: bool


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_login_rate(ip: str) -> None:
    now = time.monotonic()
    with _attempt_lock:
        attempts = _attempts[ip]
        while attempts and attempts[0] <= now - _ATTEMPT_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail="登录尝试过于频繁，请 5 分钟后再试。")


def _record_failed_login(ip: str) -> None:
    with _attempt_lock:
        _attempts[ip].append(time.monotonic())


def _clear_login_attempts(ip: str) -> None:
    with _attempt_lock:
        _attempts.pop(ip, None)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> SessionPrincipal:
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录。")
    try:
        principal = verify_session_token(token, secret=auth_signing_secret(settings))
    except (AuthenticationError, RuntimeError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    account = db.get(UserAccount, principal.user_id)
    if (
        account is None
        or not account.is_active
        or account.username != principal.username
        or account.role != principal.role
    ):
        raise HTTPException(status_code=401, detail="账号已失效，请重新登录。")
    return principal


def require_superadmin(
    principal: SessionPrincipal = Depends(get_current_user),
) -> SessionPrincipal:
    if not principal.is_superadmin:
        raise HTTPException(status_code=403, detail="只有超级管理员可以访问此页面。")
    return principal


@router.post("/login", response_model=CurrentUserResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    ip = _client_ip(request)
    _check_login_rate(ip)
    account = db.scalar(select(UserAccount).where(UserAccount.username == body.username.strip()))
    if account is None or not account.is_active or not verify_password(body.password, account.password_hash):
        _record_failed_login(ip)
        raise HTTPException(status_code=401, detail="账号或密码错误。")
    _clear_login_attempts(ip)
    settings = get_settings()
    principal = SessionPrincipal(
        user_id=account.id,
        username=account.username,
        display_name=account.display_name,
        role=account.role,
        expires_at=0,
    )
    token, _ = issue_session_token(
        principal,
        secret=auth_signing_secret(settings),
        ttl_seconds=settings.auth_session_ttl_seconds,
    )
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )
    return CurrentUserResponse(
        username=account.username,
        display_name=account.display_name,
        role=account.role.value,
        is_superadmin=principal.is_superadmin,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.auth_cookie_name, path="/")


@router.get("/me", response_model=CurrentUserResponse)
def me(principal: SessionPrincipal = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        username=principal.username,
        display_name=principal.display_name,
        role=principal.role.value,
        is_superadmin=principal.is_superadmin,
    )

