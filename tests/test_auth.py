from app.models import UserRole
from app.services.auth import (
    AuthenticationError,
    SessionPrincipal,
    hash_password,
    issue_session_token,
    verify_password,
    verify_session_token,
)


def test_password_hash_round_trip() -> None:
    encoded = hash_password("example-pass-123", salt=b"0123456789abcdef")
    assert "example-pass-123" not in encoded
    assert verify_password("example-pass-123", encoded)
    assert not verify_password("wrong-password", encoded)


def test_signed_session_round_trip_and_tamper_rejection() -> None:
    principal = SessionPrincipal(
        user_id=7,
        username="yzr01",
        display_name="yzr01",
        role=UserRole.SUPERADMIN,
        expires_at=0,
    )
    token, expires_at = issue_session_token(
        principal, secret="test-secret", ttl_seconds=600, now=1000
    )
    decoded = verify_session_token(token, secret="test-secret", now=1001)
    assert decoded.username == "yzr01"
    assert decoded.is_superadmin
    assert expires_at == 1600

    body, signature = token.split(".")
    try:
        verify_session_token(f"{body[:-1]}A.{signature}", secret="test-secret", now=1001)
        raise AssertionError("tampered token should fail")
    except AuthenticationError:
        pass
