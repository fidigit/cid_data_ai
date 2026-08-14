from __future__ import annotations

import re
from pathlib import Path
from string import Template

from app.domain.event_codes import is_valid_event_code
from app.domain.partitions import PartitionRange


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


class SqlTemplateError(ValueError):
    pass


def _identifier(value: str, label: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise SqlTemplateError(f"{label} 不是允许的 SQL 标识符。")
    return value


class EventQueryRenderer:
    """仅渲染仓库内、管理员审核过的 SQL 模板，用户不提供 SQL 或标识符。"""

    def __init__(self, template_path: Path) -> None:
        self.template_path = template_path

    def render_detail(
        self,
        *,
        source_table: str,
        partition_column: str,
        event_code_column: str,
        user_id_column: str,
        event_code: str,
        partitions: PartitionRange,
    ) -> str:
        if not is_valid_event_code(event_code):
            raise SqlTemplateError("CID 格式不合法。")
        if not self.template_path.is_file():
            raise SqlTemplateError(f"未找到 SQL 模板：{self.template_path}")

        values = {
            "source_table": _identifier(source_table, "数据表"),
            "partition_column": _identifier(partition_column, "分区字段"),
            "event_code_column": _identifier(event_code_column, "CID 字段"),
            "user_id_column": _identifier(user_id_column, "UV 字段"),
            "event_code": event_code,
            "start_partition": partitions.start,
            "end_partition": partitions.end,
        }
        try:
            return Template(self.template_path.read_text(encoding="utf-8")).substitute(values).strip()
        except KeyError as exc:
            raise SqlTemplateError(f"SQL 模板出现未知占位符：{exc.args[0]}") from exc

    @staticmethod
    def render_daily_aggregation(detail_sql: str) -> str:
        normalized = detail_sql.strip().rstrip(";")
        if not normalized.lower().startswith("select"):
            raise SqlTemplateError("明细 SQL 必须是 SELECT 查询。")
        return f"""WITH event_detail AS (
{normalized}
)
SELECT
  CAST(event_date AS STRING) AS event_date,
  COUNT(1) AS pv,
  COUNT(DISTINCT user_id) AS uv
FROM event_detail
GROUP BY event_date
;
"""
