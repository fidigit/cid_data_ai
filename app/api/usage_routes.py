from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_routes import get_current_user, require_superadmin
from app.core.config import get_settings
from app.database import get_db
from app.services.auth import SessionPrincipal
from app.services.usage_stats import (
    build_admin_usage_report,
    heartbeat_visit,
    set_daily_user_limit,
    start_visit,
)

router = APIRouter(prefix="/api/v1", tags=["usage"])


class VisitResponse(BaseModel):
    id: str
    started_at: datetime


class HeartbeatRequest(BaseModel):
    final: bool = False


class UsageUserRow(BaseModel):
    username: str
    display_name: str | None
    role: str
    page_views: int
    stay_seconds: int
    cost_estimate_count: int
    export_count: int
    consumed_amount_cny: float
    active_days: int
    last_access_at: datetime | None


class RecentVisitRow(BaseModel):
    username: str
    requester_ip: str | None
    started_at: datetime
    last_seen_at: datetime
    duration_seconds: int


class AdminUsageResponse(BaseModel):
    generated_at: datetime
    daily_user_limit_cny: float
    users: list[UsageUserRow]
    recent_visits: list[RecentVisitRow]


class DailyLimitRequest(BaseModel):
    amount_cny: float = Field(ge=0, le=1_000_000_000)


class DailyLimitResponse(BaseModel):
    daily_user_limit_cny: float


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/usage/visits", response_model=VisitResponse)
def create_visit(
    request: Request,
    principal: SessionPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VisitResponse:
    visit = start_visit(
        db,
        principal=principal,
        requester_ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return VisitResponse(id=visit.id, started_at=visit.started_at)


@router.post("/usage/visits/{visit_id}/heartbeat", response_model=VisitResponse)
def update_visit(
    visit_id: str,
    body: HeartbeatRequest,
    principal: SessionPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VisitResponse:
    visit = heartbeat_visit(db, visit_id=visit_id, principal=principal, final=body.final)
    if visit is None:
        raise HTTPException(status_code=404, detail="访问会话不存在。")
    return VisitResponse(id=visit.id, started_at=visit.started_at)


@router.get("/admin/usage", response_model=AdminUsageResponse)
def admin_usage(
    _: SessionPrincipal = Depends(require_superadmin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> AdminUsageResponse:
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    selected_end = end_date or today
    selected_start = start_date or (selected_end - timedelta(days=29))
    if selected_start > selected_end:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期。")
    return AdminUsageResponse.model_validate(
        build_admin_usage_report(
            db,
            recent_limit=limit,
            start_date=selected_start,
            end_date=selected_end,
            timezone=settings.timezone,
        )
    )


@router.put("/admin/settings/daily-limit", response_model=DailyLimitResponse)
def update_daily_limit(
    body: DailyLimitRequest,
    _: SessionPrincipal = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> DailyLimitResponse:
    return DailyLimitResponse(daily_user_limit_cny=set_daily_user_limit(db, body.amount_cny))
