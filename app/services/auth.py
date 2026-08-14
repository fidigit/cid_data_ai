from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import UserAccount, UserRole


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class SessionPrincipal:
    user_id: int
    username: str
    display_name: str | None
    role: UserRole
    expires_at: int

    @property
    def is_superadmin(self) -> bool:
        return self.role == UserRole.SUPERADMIN


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise AuthenticationError("登录会话格式无效。") from exc


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 8:
        raise ValueError("密码至少需要 8 个字符。")
    actual_salt = os.urandom(16) if salt is None else salt
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=actual_salt, n=2**14, r=8, p=1, dklen=32
    )
    return f"scrypt$16384$8$1${_encode(actual_salt)}${_encode(digest)}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded_hash.split("$", maxsplit=5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_decode(expected)),
        )
        return hmac.compare_digest(actual, _decode(expected))
    except (ValueError, TypeError, AuthenticationError):
        return False


def issue_session_token(
    principal: SessionPrincipal, *, secret: str, ttl_seconds: int, now: int | None = None
) -> tuple[str, int]:
    if not secret:
        raise RuntimeError("登录会话签名密钥尚未配置。")
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + ttl_seconds
    payload = {
        "sub": principal.user_id,
        "username": principal.username,
        "name": principal.display_name,
        "role": principal.role.value,
        "exp": expires_at,
    }
    body = _encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signature = _encode(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}", expires_at


def verify_session_token(
    token: str, *, secret: str, now: int | None = None
) -> SessionPrincipal:
    try:
        body, supplied_signature = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise AuthenticationError("登录会话格式无效。") from exc
    expected_signature = _encode(
        hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise AuthenticationError("登录会话校验失败。")
    try:
        payload = json.loads(_decode(body))
        principal = SessionPrincipal(
            user_id=int(payload["sub"]),
            username=str(payload["username"]),
            display_name=str(payload["name"]) if payload.get("name") else None,
            role=UserRole(str(payload["role"])),
            expires_at=int(payload["exp"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationError("登录会话内容无效。") from exc
    current_time = int(time.time()) if now is None else now
    if principal.expires_at <= current_time:
        raise AuthenticationError("登录已过期，请重新登录。")
    return principal


def auth_signing_secret(settings: Settings) -> str:
    if settings.auth_session_secret:
        return settings.auth_session_secret
    if settings.app_env != "production":
        return "development-only-auth-session-secret"
    raise RuntimeError("生产环境尚未配置 AUTH_SESSION_SECRET。")


def bootstrap_superadmin(db: Session, settings: Settings) -> None:
    if not settings.superadmin_username or not settings.superadmin_password_hash:
        if settings.app_env == "production":
            raise RuntimeError("生产环境尚未配置超级管理员账号。")
        return
    account = db.scalar(
        select(UserAccount).where(UserAccount.username == settings.superadmin_username)
    )
    if account is None:
        db.add(
            UserAccount(
                username=settings.superadmin_username,
                display_name=settings.superadmin_username,
                password_hash=settings.superadmin_password_hash,
                role=UserRole.SUPERADMIN,
                is_active=True,
            )
        )
    else:
        account.password_hash = settings.superadmin_password_hash
        account.role = UserRole.SUPERADMIN
        account.is_active = True
    db.commit()

