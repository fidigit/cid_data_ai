from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time
import json
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import QueryJob, QueryJobContext, SystemSetting, UsageEvent, UsageVisit, UserAccount
from app.services.auth import SessionPrincipal


def utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def start_visit(
    db: Session,
    *,
    principal: SessionPrincipal,
    requester_ip: str | None,
    user_agent: str | None,
) -> UsageVisit:
    visit = UsageVisit(
        user_id=principal.user_id,
        username=principal.username,
        requester_ip=requester_ip,
        user_agent=(user_agent or "")[:512] or None,
        started_at=utcnow(),
        last_seen_at=utcnow(),
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return visit


def heartbeat_visit(
    db: Session, *, visit_id: str, principal: SessionPrincipal, final: bool = False
) -> UsageVisit | None:
    visit = db.get(UsageVisit, visit_id)
    if visit is None or visit.user_id != principal.user_id:
        return None
    now = utcnow()
    visit.last_seen_at = now
    if final:
        visit.ended_at = now
    db.commit()
    db.refresh(visit)
    return visit


def record_usage_event(
    db: Session,
    *,
    principal: SessionPrincipal,
    event_type: str,
    amount_cny: float | None = None,
    event_code: str | None = None,
) -> UsageEvent:
    event = UsageEvent(
        user_id=principal.user_id,
        username=principal.username,
        event_type=event_type,
        amount_cny=round(amount_cny, 4) if amount_cny is not None else None,
        event_code=event_code,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


class DailyBudgetExceeded(ValueError):
    pass


def _settings_row(db: Session, *, lock: bool = False) -> SystemSetting:
    statement = select(SystemSetting).where(SystemSetting.id == 1)
    if lock:
        statement = statement.with_for_update()
    setting = db.scalar(statement)
    if setting is None:
        setting = SystemSetting(id=1, daily_user_limit_cny=0)
        db.add(setting)
        db.flush()
    return setting


def get_daily_user_limit(db: Session) -> float:
    setting = _settings_row(db)
    db.commit()
    return round(float(setting.daily_user_limit_cny or 0), 4)


def set_daily_user_limit(db: Session, amount_cny: float) -> float:
    setting = _settings_row(db, lock=True)
    setting.daily_user_limit_cny = round(max(0.0, float(amount_cny)), 4)
    db.commit()
    return setting.daily_user_limit_cny


def _utc_day_bounds(local_day: date, timezone: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone)
    start = datetime.combine(local_day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(local_day, time.max, tzinfo=zone).astimezone(UTC)
    return start, end


def reserve_daily_budget(
    db: Session,
    *,
    principal: SessionPrincipal,
    amount_cny: float,
    event_code: str,
    timezone: str,
    now: datetime | None = None,
) -> UsageEvent:
    """锁定额度设置行，在同一事务内校验并记录本次导出消费。"""
    setting = _settings_row(db, lock=True)
    current = now or utcnow()
    local_day = current.astimezone(ZoneInfo(timezone)).date()
    start, end = _utc_day_bounds(local_day, timezone)
    consumed = db.scalar(
        select(func.coalesce(func.sum(UsageEvent.amount_cny), 0.0)).where(
            UsageEvent.user_id == principal.user_id,
            UsageEvent.event_type == "export_click",
            UsageEvent.occurred_at >= start,
            UsageEvent.occurred_at <= end,
        )
    )
    limit = float(setting.daily_user_limit_cny or 0)
    requested = round(max(0.0, float(amount_cny)), 4)
    if limit > 0 and float(consumed or 0) + requested > limit + 1e-9:
        db.rollback()
        raise DailyBudgetExceeded("超过今天查询余额上限，请联系yzr")
    event = UsageEvent(
        user_id=principal.user_id,
        username=principal.username,
        event_type="export_click",
        amount_cny=requested,
        event_code=event_code,
        occurred_at=current,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _duration_seconds(visit: UsageVisit) -> int:
    end = visit.ended_at or visit.last_seen_at or visit.started_at
    start = visit.started_at
    if start.tzinfo is None and end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    elif start.tzinfo is not None and end.tzinfo is None:
        end = end.replace(tzinfo=start.tzinfo)
    return max(0, int((end - start).total_seconds()))


def build_admin_usage_report(
    db: Session,
    *,
    recent_limit: int = 100,
    recent_query_limit: int = 100,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str = "Asia/Shanghai",
) -> dict[str, object]:
    users = list(db.scalars(select(UserAccount).order_by(UserAccount.username)))
    visits_statement = select(UsageVisit).order_by(UsageVisit.started_at.desc())
    events_statement = select(UsageEvent).order_by(UsageEvent.occurred_at.desc())
    if start_date and end_date:
        start, _ = _utc_day_bounds(start_date, timezone)
        _, end = _utc_day_bounds(end_date, timezone)
        visits_statement = visits_statement.where(
            UsageVisit.started_at >= start, UsageVisit.started_at <= end
        )
        events_statement = events_statement.where(
            UsageEvent.occurred_at >= start, UsageEvent.occurred_at <= end
        )
    visits = list(db.scalars(visits_statement))
    events = list(db.scalars(events_statement))
    query_counts_statement = select(QueryJob.requester_id, func.count(QueryJob.id)).where(
        QueryJob.source == "web"
    )
    recent_queries_statement = (
        select(QueryJob, QueryJobContext)
        .outerjoin(QueryJobContext, QueryJobContext.job_id == QueryJob.id)
        .where(QueryJob.source == "web")
    )
    if start_date and end_date:
        start, _ = _utc_day_bounds(start_date, timezone)
        _, end = _utc_day_bounds(end_date, timezone)
        query_counts_statement = query_counts_statement.where(
            QueryJob.created_at >= start, QueryJob.created_at <= end
        )
        recent_queries_statement = recent_queries_statement.where(
            QueryJob.created_at >= start, QueryJob.created_at <= end
        )
    query_counts = {
        username: count
        for username, count in db.execute(query_counts_statement.group_by(QueryJob.requester_id))
    }
    recent_query_rows = db.execute(
        recent_queries_statement.order_by(QueryJob.created_at.desc(), QueryJob.id.desc())
        .limit(max(1, min(1000, recent_query_limit)))
    ).all()
    visits_by_user: dict[int, list[UsageVisit]] = defaultdict(list)
    events_by_user: dict[int, list[UsageEvent]] = defaultdict(list)
    for visit in visits:
        visits_by_user[visit.user_id].append(visit)
    for event in events:
        events_by_user[event.user_id].append(event)

    user_rows: list[dict[str, object]] = []
    for user in users:
        user_visits = visits_by_user[user.id]
        user_events = events_by_user[user.id]
        estimate_events = [item for item in user_events if item.event_type == "cost_estimate"]
        export_events = [item for item in user_events if item.event_type == "export_click"]
        last_access = max((_as_utc(item.started_at) for item in user_visits), default=None)
        user_rows.append(
            {
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role.value,
                "page_views": len(user_visits),
                "query_count": int(query_counts.get(user.username, 0)),
                "stay_seconds": sum(_duration_seconds(item) for item in user_visits),
                "cost_estimate_count": len(estimate_events),
                "export_count": len(export_events),
                "consumed_amount_cny": round(
                    sum(float(item.amount_cny or 0) for item in export_events), 4
                ),
                "active_days": len(
                    {
                        _as_utc(item.started_at).astimezone(ZoneInfo(timezone)).date()
                        for item in user_visits
                        if _as_utc(item.started_at) is not None
                    }
                ),
                "last_access_at": last_access,
            }
        )

    return {
        "generated_at": utcnow(),
        "daily_user_limit_cny": get_daily_user_limit(db),
        "users": user_rows,
        "recent_visits": [
            {
                "username": item.username,
                "requester_ip": item.requester_ip,
                "started_at": _as_utc(item.started_at),
                "last_seen_at": _as_utc(item.last_seen_at),
                "duration_seconds": _duration_seconds(item),
            }
            for item in visits[:recent_limit]
        ],
        "recent_queries": [
            _query_filter_snapshot(job, context)
            for job, context in recent_query_rows
        ],
    }


def _saved_json(value: str | None, fallback):
    try:
        parsed = json.loads(value) if value else fallback
    except (TypeError, ValueError):
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def _query_filter_snapshot(job: QueryJob, context: QueryJobContext | None) -> dict[str, object]:
    filters = _saved_json(context.filters_json if context else None, {})
    codes = _saved_json(context.event_codes_json if context else None, [])
    return {
        "job_id": job.id,
        "username": job.requester_id,
        "created_at": _as_utc(job.created_at),
        "status": job.status.value,
        "log_type": context.log_type if context else "client",
        "event_codes": [str(code) for code in codes] if codes else [job.event_code],
        "partition_start": context.partition_start if context else "",
        "partition_end": context.partition_end if context else "",
        "systems": filters.get("systems", []),
        "version_mode": filters.get("version_mode") or "",
        "versions": filters.get("versions", []),
        "new_users": filters.get("new_users", [0, 1]),
        "value_fields": filters.get("value_fields", []),
        "value_filters": filters.get("value_filters", []),
    }


def query_sql_for_job(db: Session, job_id: str) -> tuple[str, str] | None:
    """按提交时保存的参数重建明细与聚合 SQL；旧记录缺少上下文时不可重建。"""
    from app.core.config import get_settings
    from app.domain.partitions import PartitionRange
    from app.services.query_plan import build_query_plan

    row = db.execute(
        select(QueryJob, QueryJobContext)
        .join(QueryJobContext, QueryJobContext.job_id == QueryJob.id)
        .where(QueryJob.id == job_id, QueryJob.source == "web")
    ).first()
    if row is None:
        return None
    job, context = row
    codes = _saved_json(context.event_codes_json, []) or [job.event_code]
    filters = _saved_json(context.filters_json, {})
    return build_query_plan(
        get_settings(), codes,
        PartitionRange(context.partition_start, context.partition_end),
        context.log_type, filters, context.export_limit,
    )
