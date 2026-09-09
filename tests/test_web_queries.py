from contextlib import contextmanager
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth_routes import get_current_user
from app.core.config import Settings
from app.database import Base, get_db, migrate_log_type
from app.domain.event_codes import extract_unique_event_code, EventCodeExtractionError
from app.domain.partitions import PartitionRange
from app.infrastructure.odps_gateway import QueryCost, QueryStream
from app.main import app
from app.models import QueryJobContext, UserRole
from app.services.auth import SessionPrincipal
from app.services.cost_estimates import issue_cost_estimate_token, verify_cost_estimate_token, CostEstimateTokenError
from app.services.query_plan import build_query_plan
from app.services.usage_stats import DailyBudgetExceeded
from app.workers.tasks import execute_query_job


def test_web_plan_and_encoding():
    assert extract_unique_event_code("帮我查 70081134 数据", "web") == "70081134"
    for question in ("70081134 70081133", "1700930", "x70081134", "700811340", "70081134_0001"):
        with pytest.raises(EventCodeExtractionError):
            extract_unique_event_code(question, "web")
    with pytest.raises(EventCodeExtractionError):
        extract_unique_event_code("70081134", "client")
    detail, aggregate = build_query_plan(Settings(_env_file=None), "70081134", PartitionRange("20260901", "20260907"), "web")
    assert "yy_websdkprotocol_original" in detail
    assert "BETWEEN '20260901' AND '20260907'" in detail
    assert "IN ('70081134')" in detail
    assert "GROUP BY dt, eventid" in aggregate
    assert "COUNT(DISTINCT uid)" in aggregate
    assert "product_id" not in detail


def test_type_bound_token():
    values = dict(secret="test", requester_id="member", event_code="70081134", partition_start="20260901", partition_end="20260901")
    token, _ = issue_cost_estimate_token(**values, log_type="web", estimated_amount_cny=1, ttl_seconds=60)
    assert verify_cost_estimate_token(token, **values, log_type="web").log_type == "web"
    with pytest.raises(CostEstimateTokenError):
        verify_cost_estimate_token(token, **values, log_type="client")


def test_existing_database_upgrade_preserves_rows():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE query_job_contexts (job_id TEXT PRIMARY KEY, days INTEGER)"))
        conn.execute(text("INSERT INTO query_job_contexts VALUES ('old-job', 7)"))
    migrate_log_type(engine)
    migrate_log_type(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT job_id, days, log_type FROM query_job_contexts")).one() == ("old-job", 7, "client")


@pytest.mark.parametrize("empty", [False, True])
def test_web_estimate_execute_download_end_to_end(monkeypatch, tmp_path, empty):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(_env_file=None, odps_access_id="fake", odps_access_key_secret="fake", odps_project="fake", odps_endpoint="fake", artifacts_dir=tmp_path)
    estimated, executed, charges = [], [], []

    class Gateway:
        def __init__(self, settings): pass
        def estimate_sql_cost(self, sql):
            estimated.append(sql)
            return QueryCost(1024**3, 1, 0)
        @contextmanager
        def open_rows(self, sql):
            executed.append(sql)
            if "COUNT(DISTINCT uid)" in sql:
                yield QueryStream(("event_date", "eventid", "uv", "pv"), [] if empty else [("20260801", "70081134", 1, 2)], "aggregate-id")
            else:
                yield QueryStream(("uid", "time", "act_type", "eventid", "dt"), [] if empty else [("001", 123, "=1+1", "70081134", "20260801"), ("001", 124, "click", "70081134", "20260801")], "detail-id")

    def db_dependency():
        with sessions() as db: yield db
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = lambda: SessionPrincipal(user_id=1, username="member", display_name=None, role=UserRole.MEMBER, expires_at=9999999999)
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.OdpsGateway", Gateway)
    monkeypatch.setattr("app.api.routes.record_usage_event", lambda *a, **kw: None)
    monkeypatch.setattr("app.api.routes.reserve_daily_budget", lambda *a, **kw: charges.append(kw["amount_cny"]))
    monkeypatch.setattr("app.api.routes.dispatch_query_job", lambda *a: None)
    monkeypatch.setattr("app.workers.tasks.SessionLocal", sessions)
    monkeypatch.setattr("app.workers.tasks.get_settings", lambda: settings)
    monkeypatch.setattr("app.workers.tasks.OdpsGateway", Gateway)
    try:
        client = TestClient(app)
        body = dict(question="看看70081134数据", log_type="web", start_date="2026-08-01", end_date="2026-08-01")
        estimate = client.post("/api/v1/query-estimates", json=body)
        assert estimate.status_code == 200, estimate.text
        assert estimate.json()["estimated_amount_cny"] == .6
        assert len(estimated) == 2
        def reject_budget(*args, **kwargs):
            raise DailyBudgetExceeded("超过今天查询余额上限，请联系yzr")
        monkeypatch.setattr("app.api.routes.reserve_daily_budget", reject_budget)
        blocked = client.post("/api/v1/query-requests", json=body | {"estimate_token": estimate.json()["estimate_token"]})
        assert blocked.status_code == 429
        assert not executed
        monkeypatch.setattr("app.api.routes.reserve_daily_budget", lambda *a, **kw: charges.append(kw["amount_cny"]))
        submission = client.post("/api/v1/query-requests", json=body | {"estimate_token": estimate.json()["estimate_token"]})
        assert submission.status_code == 202, submission.text
        job_id = submission.json()["id"]
        assert submission.json()["log_type"] == "web"
        with sessions() as db:
            assert db.get(QueryJobContext, job_id).log_type == "web"
        execute_query_job.run(job_id)
        assert set(executed) == set(estimated)
        assert charges == [.6]
        result = client.get(f"/api/v1/jobs/{job_id}").json()
        assert result["status"] == "succeeded", result
        assert result["detail_row_count"] == (0 if empty else 2)
        if not empty:
            assert result["aggregation"] == [{"event_date": "20260801", "pv": 2, "uv": 1}]
        download = client.get(f"/api/v1/jobs/{job_id}/download")
        assert download.status_code == 200
        assert "web_70081134" in download.headers["content-disposition"]
        with ZipFile(next(tmp_path.rglob("*.xlsx"))) as workbook:
            summary = workbook.read("xl/worksheets/sheet2.xml").decode()
            assert "eventid" in summary and "70081134" in summary
            if not empty:
                assert "SUM(B5:B5)" in summary
                assert "SUM(C5:C5)" in summary
                assert "'=1+1" in workbook.read("xl/worksheets/sheet1.xml").decode()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
