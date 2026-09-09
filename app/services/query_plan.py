"""SQL plans shared by cost estimation and execution."""
from pathlib import Path
from string import Template

from app.infrastructure.sql_renderer import EventQueryRenderer
from app.domain.event_codes import is_valid_event_code

SQL_ROOT = Path(__file__).resolve().parents[2] / "sql"


def build_query_plan(settings, event_code, partitions, log_type="client"):
    if log_type not in ("client", "web"):
        raise ValueError("日志类型无效。")
    if not is_valid_event_code(event_code, log_type):
        raise ValueError("事件编码格式不合法。")
    renderer = EventQueryRenderer(SQL_ROOT / "event_detail.sql")
    if log_type == "web":
        detail = Template((SQL_ROOT / "web_event_detail.sql").read_text(encoding="utf-8")).substitute(
            event_code=event_code, start_partition=partitions.start, end_partition=partitions.end
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
            event_code=event_code, partitions=partitions,
        )
        aggregate = renderer.render_daily_aggregation(detail)
    return detail, aggregate
