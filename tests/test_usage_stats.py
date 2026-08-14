from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import UserAccount, UserRole
from app.services.auth import SessionPrincipal
from app.services.usage_stats import (
    DailyBudgetExceeded,
    build_admin_usage_report,
    heartbeat_visit,
    record_usage_event,
    reserve_daily_budget,
    set_daily_user_limit,
    start_visit,
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
