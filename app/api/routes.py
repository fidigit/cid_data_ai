from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.schemas import (
    DailyAggregationResponse,
    JobResponse,
    QueryEstimateRequest,
    QueryEstimateResponse,
    QueryRequest,
)
from app.api.auth_routes import get_current_user, require_superadmin
from app.core.config import Settings, get_settings
from app.database import get_db
from app.domain.event_codes import EventCodeExtractionError, extract_unique_event_code, normalize_question
from app.domain.partitions import PartitionRange, calendar_date_range, latest_calendar_days
from app.infrastructure.odps_gateway import OdpsGateway
from app.infrastructure.sql_renderer import EventQueryRenderer, SqlTemplateError
from app.models import JobStatus, QueryJob
from app.services.cost_estimates import (
    CostEstimateTokenError,
    issue_cost_estimate_token,
    verify_cost_estimate_token,
)
from app.services.auth import SessionPrincipal
from app.services.query_jobs import admin_summary, create_job, get_daily_aggregation, record_download
from app.services.task_dispatch import dispatch_query_job
from app.services.usage_stats import DailyBudgetExceeded, record_usage_event, reserve_daily_budget

router = APIRouter(prefix="/api/v1")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _client_ip(request: Request) -> str | None:
    # 生产环境只允许受信任 Nginx/Ingress 写入转发地址；不要直接信任公网 X-Forwarded-For。
    return request.client.host if request.client else None


def _job_response(db: Session, job: QueryJob) -> JobResponse:
    aggregation = (
        [
            DailyAggregationResponse(event_date=item.event_date, pv=item.pv, uv=item.uv)
            for item in get_daily_aggregation(db, job.id)
        ]
        if job.status == JobStatus.SUCCEEDED
        else []
    )
    return JobResponse(
        id=job.id,
        status=job.status,
        event_code=job.event_code,
        created_at=job.created_at,
        detail_row_count=job.detail_row_count,
        error_message=job.error_message if job.status == JobStatus.FAILED else None,
        aggregation=aggregation,
    )


def _signing_secret(settings: Settings) -> str:
    if settings.cost_estimate_token_secret:
        return settings.cost_estimate_token_secret
    if settings.app_env != "production":
        return "development-only-cost-estimate-secret"
    raise HTTPException(status_code=503, detail="生产环境尚未配置费用评估签名密钥。")


def _query_context(
    question: str,
    days: int,
    settings: Settings,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[str, PartitionRange, str, str, int]:
    try:
        normalized_question = normalize_question(question)
        event_code = extract_unique_event_code(question)
        today = datetime.now(ZoneInfo(settings.timezone)).date()
        if (start_date is None) != (end_date is None):
            raise ValueError("开始日期和结束日期必须同时填写。")
        if start_date is not None and end_date is not None:
            partitions = calendar_date_range(
                today=today,
                start_date=start_date,
                end_date=end_date,
                fmt=settings.partition_date_format,
            )
            resolved_days = (end_date - start_date).days + 1
        else:
            partitions = latest_calendar_days(today, settings.partition_date_format, days)
            resolved_days = days
        sql = EventQueryRenderer(PROJECT_ROOT / "sql" / "event_detail.sql").render_detail(
            source_table=settings.data_source_table,
            partition_column=settings.data_partition_column,
            event_code_column=settings.data_event_code_column,
            user_id_column=settings.data_user_id_column,
            event_code=event_code,
            partitions=partitions,
        )
    except EventCodeExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SqlTemplateError as exc:
        raise HTTPException(status_code=503, detail=f"查询模板配置错误：{exc}") from exc
    return event_code, partitions, sql, normalized_question, resolved_days


@router.post("/query-estimates", response_model=QueryEstimateResponse)
def estimate_query(
    request_body: QueryEstimateRequest,
    request: Request,
    principal: SessionPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QueryEstimateResponse:
    settings = get_settings()
    event_code, partitions, sql, _, resolved_days = _query_context(
        request_body.question,
        request_body.days,
        settings,
        request_body.start_date,
        request_body.end_date,
    )
    record_usage_event(
        db,
        principal=principal,
        event_type="cost_estimate",
        event_code=event_code,
    )
    try:
        cost = OdpsGateway(settings).estimate_sql_cost(sql)
    except Exception as exc:
        message = str(exc).strip()[:300] or type(exc).__name__
        raise HTTPException(status_code=502, detail=f"ODPS 费用评估失败：{message}") from exc

    input_size_gib = cost.input_size_bytes / (1024**3)
    estimated_amount = input_size_gib * settings.cost_estimate_price_per_gib_cny
    token, expires_at = issue_cost_estimate_token(
        secret=_signing_secret(settings),
        requester_id=principal.username,
        event_code=event_code,
        partition_start=partitions.start,
        partition_end=partitions.end,
        estimated_amount_cny=estimated_amount,
        ttl_seconds=settings.cost_estimate_token_ttl_seconds,
    )
    return QueryEstimateResponse(
        event_code=event_code,
        days=resolved_days,
        partition_start=partitions.start,
        partition_end=partitions.end,
        input_size_bytes=cost.input_size_bytes,
        input_size_gib=round(input_size_gib, 6),
        complexity=cost.complexity,
        udf_count=cost.udf_count,
        estimated_amount_cny=round(estimated_amount, 4),
        price_per_gib_cny=settings.cost_estimate_price_per_gib_cny,
        expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
        estimate_token=token,
    )


@router.post("/query-requests", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_query(
    request_body: QueryRequest,
    request: Request,
    principal: SessionPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobResponse:
    settings = get_settings()
    event_code, partitions, _, normalized_question, resolved_days = _query_context(
        request_body.question,
        request_body.days,
        settings,
        request_body.start_date,
        request_body.end_date,
    )
    try:
        claims = verify_cost_estimate_token(
            request_body.estimate_token,
            secret=_signing_secret(settings),
            requester_id=principal.username,
            event_code=event_code,
            partition_start=partitions.start,
            partition_end=partitions.end,
        )
    except CostEstimateTokenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        reserve_daily_budget(
            db,
            principal=principal,
            amount_cny=claims.estimated_amount_cny,
            event_code=event_code,
            timezone=settings.timezone,
        )
    except DailyBudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    job = create_job(
        db,
        source="web",
        requester_id=principal.username,
        requester_name=principal.display_name,
        requester_ip=_client_ip(request),
        raw_question=normalized_question,
        event_code=event_code,
        partition_start=partitions.start,
        partition_end=partitions.end,
        days=resolved_days,
        estimated_amount_cny=claims.estimated_amount_cny,
    )
    try:
        dispatch_query_job(job.id, settings)
    except Exception as exc:
        # 保留任务记录，方便后台发现 Redis/Worker 不可用问题。
        raise HTTPException(status_code=503, detail="任务队列不可用，请稍后重试。") from exc
    return _job_response(db, job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    principal: SessionPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobResponse:
    job = db.get(QueryJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在。")
    if job.requester_id != principal.username and not principal.is_superadmin:
        raise HTTPException(status_code=403, detail="无权查看该任务。")
    return _job_response(db, job)


@router.get("/jobs/{job_id}/download")
def download_job(
    job_id: str,
    request: Request,
    principal: SessionPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    job = db.get(QueryJob, job_id)
    if job is None or job.status != JobStatus.SUCCEEDED or not job.artifact_path:
        raise HTTPException(status_code=404, detail="结果文件尚不可下载。")
    if job.requester_id != principal.username and not principal.is_superadmin:
        raise HTTPException(status_code=403, detail="无权下载该任务。")
    artifact = Path(job.artifact_path)
    if not artifact.is_file():
        raise HTTPException(status_code=410, detail="结果文件已过期或被清理。")
    record_download(
        db,
        job=job,
        requester_id=principal.username,
        requester_ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return FileResponse(
        artifact,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=artifact.name,
    )


@router.get("/admin/stats")
def get_admin_stats(
    _: SessionPrincipal = Depends(require_superadmin), db: Session = Depends(get_db)
) -> dict[str, int]:
    return admin_summary(db)
