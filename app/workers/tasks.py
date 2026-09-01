from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.database import SessionLocal
from app.domain.partitions import PartitionRange
from app.infrastructure.odps_gateway import OdpsGateway
from app.infrastructure.sql_renderer import EventQueryRenderer
from app.models import JobStatus, QueryJob, QueryJobContext
from app.services.query_jobs import (
    mark_failed,
    mark_running,
    mark_succeeded,
    replace_daily_aggregation,
)
from app.services.report_builder import build_xlsx
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(), max_retries=0)
def execute_query_job(self, job_id: str) -> None:
    """按 job_id 幂等处理。重试策略应在确认 ODPS/企业微信限额后再单独配置。"""
    settings = get_settings()
    db = SessionLocal()
    try:
        job = db.get(QueryJob, job_id)
        if job is None or job.status != JobStatus.QUEUED:
            return
        mark_running(db, job)
        settings.validate_odps_ready()

        context = db.get(QueryJobContext, job.id)
        if context is None:
            raise RuntimeError("查询任务缺少分区上下文。")
        partitions = PartitionRange(start=context.partition_start, end=context.partition_end)
        renderer = EventQueryRenderer(Path("sql/event_detail.sql"))
        detail_sql = renderer.render_detail(
            source_table=settings.data_source_table,
            partition_column=settings.data_partition_column,
            event_code_column=settings.data_event_code_column,
            user_id_column=settings.data_user_id_column,
            event_code=job.event_code,
            partitions=partitions,
        )
        aggregation_sql = renderer.render_daily_aggregation(detail_sql)
        odps = OdpsGateway(settings)

        with odps.open_rows(aggregation_sql) as aggregate_stream:
            aggregation = [
                dict(zip(aggregate_stream.columns, row, strict=True)) for row in aggregate_stream.rows
            ]
        aggregation.sort(key=lambda item: str(item.get("event_date") or ""))
        replace_daily_aggregation(db, job_id=job.id, rows=aggregation)

        artifact_path = (
            settings.artifacts_dir
            / job.id
            / f"{job.event_code}_{partitions.start}_{partitions.end}.xlsx"
        )
        with odps.open_rows(detail_sql) as detail_stream:
            row_count = build_xlsx(
                destination=artifact_path,
                event_code=job.event_code,
                partition_start=partitions.start,
                partition_end=partitions.end,
                aggregation=aggregation,
                detail_columns=detail_stream.columns,
                detail_rows=detail_stream.rows,
                max_rows=settings.max_export_rows,
            )
            mark_succeeded(
                db,
                job,
                artifact_path=str(artifact_path),
                detail_row_count=row_count,
                odps_instance_id=detail_stream.instance_id,
            )
        # TODO: 选择企业微信接入模式后，在此调用 WeComOutboundGateway 回传文件或短期链接。
    except Exception as exc:
        job = db.get(QueryJob, job_id)
        if job is not None:
            mark_failed(db, job, error_code=type(exc).__name__, error_message=str(exc))
        raise
    finally:
        db.close()
