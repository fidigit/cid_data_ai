from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import UserAccount, UserRole
from app.services.auth import hash_password


def test_login_cookie_and_admin_role_enforcement() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all(
        [
            UserAccount(
                username="member01",
                display_name="成员一",
                password_hash=hash_password("member-pass"),
                role=UserRole.MEMBER,
            ),
            UserAccount(
                username="admin01",
                display_name="管理员",
                password_hash=hash_password("admin-pass"),
                role=UserRole.SUPERADMIN,
            ),
        ]
    )
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            unauthenticated = client.get("/api/v1/auth/me")
            assert unauthenticated.status_code == 401

            member_login = client.post(
                "/api/v1/auth/login",
                json={"username": "member01", "password": "member-pass"},
            )
            assert member_login.status_code == 200
            assert client.get("/api/v1/auth/me").json()["username"] == "member01"
            assert client.get("/api/v1/admin/usage").status_code == 403

            admin_login = client.post(
                "/api/v1/auth/login",
                json={"username": "admin01", "password": "admin-pass"},
            )
            assert admin_login.status_code == 200
            assert client.get("/api/v1/admin/usage").status_code == 200

            assert client.post("/api/v1/auth/logout").status_code == 204
            assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        app.dependency_overrides.clear()
        db.close()
