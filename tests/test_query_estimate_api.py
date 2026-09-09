from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db
from app.api.auth_routes import get_current_user
from app.infrastructure.odps_gateway import OdpsGateway
from app.main import app
from app.models import JobStatus
from app.models import UserRole
from app.services.auth import SessionPrincipal


class FakeOdpsClient:
    def execute_sql_cost(self, sql: str):
        assert "90056_0001" in sql
        return SimpleNamespace(input_size=5 * 1024**3, complexity=2, udf_num=0)


def test_estimate_is_required_before_real_query(monkeypatch) -> None:
    monkeypatch.setattr(OdpsGateway, "_client", lambda self: FakeOdpsClient())
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(get=lambda *args: None)
    app.dependency_overrides[get_current_user] = lambda: SessionPrincipal(
        user_id=1,
        username="user-1",
        display_name="测试用户",
        role=UserRole.MEMBER,
        expires_at=9999999999,
    )
    queued_ids: list[str] = []

    fake_job = SimpleNamespace(
        id="job-1",
        status=JobStatus.QUEUED,
        event_code="90056_0001",
        created_at=datetime.now(UTC),
        detail_row_count=None,
        error_message=None,
    )
    monkeypatch.setattr("app.api.routes.create_job", lambda *args, **kwargs: fake_job)
    monkeypatch.setattr("app.api.routes.dispatch_query_job", lambda job_id, settings: queued_ids.append(job_id))
    monkeypatch.setattr("app.api.routes.record_usage_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.api.routes.reserve_daily_budget", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.api.routes.get_daily_aggregation", lambda *args, **kwargs: [])

    try:
        with TestClient(app) as client:
            estimate_response = client.post(
                "/api/v1/query-estimates", json={"question": "看看90056_0001数据", "days": 1}
            )
            assert estimate_response.status_code == 200
            estimate = estimate_response.json()
            assert estimate["input_size_bytes"] == 10 * 1024**3
            assert estimate["input_size_gib"] == 10
            assert estimate["estimated_amount_cny"] == 3.0

            rejected = client.post(
                "/api/v1/query-requests",
                json={
                    "question": "看看90056_0002数据",
                    "days": 1,
                    "estimate_token": estimate["estimate_token"],
                },
            )
            assert rejected.status_code == 409
            assert queued_ids == []

            changed_window = client.post(
                "/api/v1/query-requests",
                json={
                    "question": "看看90056_0001数据",
                    "days": 7,
                    "estimate_token": estimate["estimate_token"],
                },
            )
            assert changed_window.status_code == 409
            assert queued_ids == []

            accepted = client.post(
                "/api/v1/query-requests",
                json={
                    "question": "看看90056_0001数据",
                    "days": 1,
                    "estimate_token": estimate["estimate_token"],
                },
            )
            assert accepted.status_code == 202
            assert queued_ids == ["job-1"]
    finally:
        app.dependency_overrides.clear()


def test_query_window_is_limited_to_seven_days() -> None:
    app.dependency_overrides[get_current_user] = lambda: SessionPrincipal(
        user_id=1,
        username="user-1",
        display_name=None,
        role=UserRole.MEMBER,
        expires_at=9999999999,
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/query-estimates", json={"question": "看看90056_0001数据", "days": 8}
            )
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_explicit_date_range_rejects_today_and_longer_than_seven_days(monkeypatch) -> None:
    monkeypatch.setattr(OdpsGateway, "_client", lambda self: FakeOdpsClient())
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: SessionPrincipal(
        user_id=1,
        username="user-1",
        display_name=None,
        role=UserRole.MEMBER,
        expires_at=9999999999,
    )
    today = date.today()
    try:
        with TestClient(app) as client:
            today_response = client.post(
                "/api/v1/query-estimates",
                json={
                    "question": "看看90056_0001数据",
                    "start_date": today.isoformat(),
                    "end_date": today.isoformat(),
                },
            )
            assert today_response.status_code == 422
            long_response = client.post(
                "/api/v1/query-estimates",
                json={
                    "question": "看看90056_0001数据",
                    "start_date": (today - timedelta(days=8)).isoformat(),
                    "end_date": (today - timedelta(days=1)).isoformat(),
                },
            )
            assert long_response.status_code == 422
    finally:
        app.dependency_overrides.clear()
