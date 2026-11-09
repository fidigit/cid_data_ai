from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import UserAccount, UserRole
from app.services.query_jobs import create_job
from app.services.auth import SessionPrincipal
from app.services.usage_stats import (
    DailyBudgetExceeded,
    build_admin_usage_report,
    heartbeat_visit,
    record_usage_event,
    reserve_daily_budget,
    set_daily_user_limit,
    start_visit,
    query_sql_for_job,
)


def test_usage_report_aggregates_per_user() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = UserAccount(
            username="member01",
            display_name="成员一",
            password_hash="unused",
            role=UserRole.MEMBER,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        principal = SessionPrincipal(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,
            expires_at=9999999999,
        )
        visit = start_visit(
            db, principal=principal, requester_ip="127.0.0.1", user_agent="pytest"
        )
        visit.started_at = datetime.now(UTC) - timedelta(seconds=90)
        db.commit()
        heartbeat_visit(db, visit_id=visit.id, principal=principal, final=True)
        record_usage_event(
            db,
            principal=principal,
            event_type="cost_estimate",
            amount_cny=1.25,
            event_code="90056_0001",
        )
        record_usage_event(
            db,
            principal=principal,
            event_type="export_click",
            amount_cny=1.25,
            event_code="90056_0001",
        )

        report = build_admin_usage_report(db)
        row = report["users"][0]
        assert row["page_views"] == 1
        assert row["stay_seconds"] >= 89
        assert row["cost_estimate_count"] == 1
        assert row["export_count"] == 1
        assert row["consumed_amount_cny"] == 1.25
        assert row["last_access_at"].tzinfo is not None
        assert report["recent_visits"][0]["started_at"].tzinfo is not None


def test_admin_usage_counts_submitted_queries_and_limits_filter_history() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = UserAccount(username="member01", password_hash="unused", role=UserRole.MEMBER)
        db.add(user)
        db.commit()
        now = datetime.now(UTC)
        for index in range(3):
            job = create_job(
                db, source="web", requester_id="member01", requester_name=None,
                requester_ip=None, raw_question="170035", event_code="170035",
                event_codes=["170035", "90056"], partition_start="20261101",
                partition_end="20261102", days=2, estimated_amount_cny=0.1,
                filters={"systems": ["ios"], "version_mode": "greater_equal",
                         "versions": ["16.4.1"], "new_users": [1],
                         "value_filters": [{"field": "value1", "conditions": [
                             {"operator": "ge", "target": "100"}]}]},
            )
            job.created_at = now - timedelta(days=4 if index == 0 else 0, seconds=2 - index)
            db.commit()

        report = build_admin_usage_report(
            db, start_date=now.date(), end_date=now.date(),
            timezone="UTC", recent_query_limit=1,
        )
        assert report["users"][0]["query_count"] == 2
        assert len(report["recent_queries"]) == 1
        query = report["recent_queries"][0]
        assert query["username"] == "member01"
        assert query["job_id"] == job.id
        assert query["event_codes"] == ["170035", "90056"]
        assert query["partition_start"] == "20261101"
        assert query["systems"] == ["ios"]
        assert query["versions"] == ["16.4.1"]
        assert query["new_users"] == [1]
        assert query["value_filters"][0]["field"] == "value1"
        assert "raw_question" not in query
        assert "sql" not in query

        detail_sql, aggregate_sql = query_sql_for_job(db, job.id)
        assert "170035" in detail_sql and "90056" in detail_sql
        assert "20261101" in detail_sql and "20261102" in detail_sql
        assert "value1" in detail_sql
        assert "COUNT" in aggregate_sql.upper()


def test_daily_budget_applies_to_every_role() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = UserAccount(
            username="admin01",
            display_name="管理员",
            password_hash="unused",
            role=UserRole.SUPERADMIN,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        principal = SessionPrincipal(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,
            expires_at=9999999999,
        )
        set_daily_user_limit(db, 2.0)
        reserve_daily_budget(
            db,
            principal=principal,
            amount_cny=1.25,
            event_code="1700930_0001",
            timezone="Asia/Shanghai",
        )
        with pytest.raises(DailyBudgetExceeded, match="联系yzr"):
            reserve_daily_budget(
                db,
                principal=principal,
                amount_cny=0.76,
                event_code="1700930_0001",
                timezone="Asia/Shanghai",
            )
