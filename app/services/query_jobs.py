from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    DailyAggregation,
    DownloadLog,
    JobStatus,
    QueryJob,
    QueryJobContext,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_job(
    db: Session,
    *,
    source: str,
    requester_id: str,
    requester_name: str | None,
    requester_ip: str | None,
    raw_question: str,
    event_code: str,
    partition_start: str,
    partition_end: str,
    days: int,
    estimated_amount_cny: float,
    log_type: str = "client",
) -> QueryJob:
    job = QueryJob(
        source=source,
        requester_id=requester_id,
        requester_name=requester_name,
        requester_ip=requester_ip,
        raw_question=raw_question,
        event_code=event_code,
    )
    db.add(job)
    db.flush()
    db.add(
        QueryJobContext(
            log_type=log_type,
            job_id=job.id,
            partition_start=partition_start,
            partition_end=partition_end,
            days=days,
            estimated_amount_cny=estimated_amount_cny,
        )
    )
    db.commit()
    db.refresh(job)
    return job


def replace_daily_aggregation(
    db: Session, *, job_id: str, rows: list[dict[str, object]]
) -> None:
    db.execute(delete(DailyAggregation).where(DailyAggregation.job_id == job_id))
    for row in rows:
        db.add(
            DailyAggregation(
                job_id=job_id,
                event_date=str(row.get("event_date") or ""),
                pv=int(row.get("pv") or 0),
                uv=int(row.get("uv") or 0),
            )
        )
    db.commit()


def get_daily_aggregation(db: Session, job_id: str) -> list[DailyAggregation]:
    return list(
        db.scalars(
            select(DailyAggregation)
            .where(DailyAggregation.job_id == job_id)
            .order_by(DailyAggregation.event_date)
        )
    )


def mark_running(db: Session, job: QueryJob) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = utcnow()
    db.commit()


def mark_succeeded(
    db: Session,
    job: QueryJob,
    *,
    artifact_path: str,
    detail_row_count: int,
    odps_instance_id: str | None,
) -> None:
    job.status = JobStatus.SUCCEEDED
    job.artifact_path = artifact_path
    job.detail_row_count = detail_row_count
    job.odps_instance_id = odps_instance_id
    job.completed_at = utcnow()
    db.commit()


def mark_failed(db: Session, job: QueryJob, error_code: str, error_message: str) -> None:
    job.status = JobStatus.FAILED
    job.error_code = error_code
    job.error_message = error_message[:2000]
    job.completed_at = utcnow()
    db.commit()


def record_download(
    db: Session,
    *,
    job: QueryJob,
    requester_id: str,
    requester_ip: str | None,
    user_agent: str | None,
) -> None:
    db.add(
        DownloadLog(
            job_id=job.id,
            requester_id=requester_id,
            requester_ip=requester_ip,
            user_agent=user_agent,
        )
    )
    db.commit()


def admin_summary(db: Session) -> dict[str, int]:
    return {
        "query_count": db.scalar(select(func.count(QueryJob.id))) or 0,
        "query_users": db.scalar(select(func.count(func.distinct(QueryJob.requester_id)))) or 0,
        "download_count": db.scalar(select(func.count(DownloadLog.id))) or 0,
        "download_users": db.scalar(select(func.count(func.distinct(DownloadLog.requester_id)))) or 0,
        "failed_count": db.scalar(
            select(func.count(QueryJob.id)).where(QueryJob.status == JobStatus.FAILED)
        )
        or 0,
    }
