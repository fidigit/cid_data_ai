"""SQL plans shared by cost estimation and execution."""
from pathlib import Path
from string import Template

from app.infrastructure.sql_renderer import EventQueryRenderer
from app.domain.event_codes import is_valid_event_code

SQL_ROOT = Path(__file__).resolve().parents[2] / "sql"


def build_query_plan(settings, event_code, partitions, log_type="client", filters=None, row_limit=None):
    if log_type not in ("client", "web"):
        raise ValueError("日志类型无效。")
    codes = event_code if isinstance(event_code, list) else [event_code]
    if not codes or len(codes) > 50 or not all(is_valid_event_code(code, log_type) for code in codes):
        raise ValueError("事件编码格式不合法。")
    renderer = EventQueryRenderer(SQL_ROOT / "event_detail.sql")
    if log_type == "web":
        detail = Template((SQL_ROOT / "web_event_detail.sql").read_text(encoding="utf-8")).substitute(
            event_codes=", ".join(f"'{code}'" for code in codes), start_partition=partitions.start, end_partition=partitions.end
        ).strip()
        aggregate = f"""WITH tmp AS ({detail.rstrip(';')})
SELECT CAST(dt AS STRING) AS event_date, eventid,
       COUNT(DISTINCT uid) AS uv, COUNT(1) AS pv
FROM tmp GROUP BY dt, eventid;"""
    else:
        detail = renderer.render_detail(
            source_table=settings.data_source_table,
            partition_column=settings.data_partition_column,
            event_code_column=settings.data_event_code_column,
            user_id_column=settings.data_user_id_column,
            event_code=codes, partitions=partitions, filters=filters,
        )
        aggregate = renderer.render_daily_aggregation(detail)
    from app.domain.query_filters import export_limit
    limit = export_limit(settings) if row_limit is None else max(1, min(200_000, int(row_limit)))
    # Aggregate the complete result; limit only the returned detail rows.
    detail = detail.rstrip().rstrip(';') + f"\nLIMIT {limit};"
    return detail, aggregate


def plan_fingerprint(plan):
    import hashlib
    return hashlib.sha256("\n".join(plan).encode("utf-8")).hexdigest()
