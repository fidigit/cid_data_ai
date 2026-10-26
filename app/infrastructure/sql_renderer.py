from __future__ import annotations

import re
from pathlib import Path
from string import Template

from app.domain.event_codes import is_valid_event_code
from app.domain.partitions import PartitionRange
from app.domain.query_filters import effective_filters
from app.infrastructure.filter_sql import render_value_filters


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
        filters=None,
    ) -> str:
        codes = event_code if isinstance(event_code, list) else [event_code]
        if not codes or len(codes) > 50 or not all(is_valid_event_code(code) for code in codes):
            raise SqlTemplateError("CID 格式不合法。")
        if not self.template_path.is_file():
            raise SqlTemplateError(f"未找到 SQL 模板：{self.template_path}")

        selected = effective_filters(filters)
        predicates = []
        if len(selected.new_users) == 1:
            predicates.append(f"AND is_new = {selected.new_users[0]}")
        condition = render_value_filters(selected)
        if condition:
            predicates.append("AND " + condition)
        if selected.systems:
            literals = ", ".join("'" + item + "'" for item in selected.systems)
            predicates.append(f"AND sys IN ({literals})")
        if selected.versions:
            if selected.version_mode in ("greater", "greater_equal"):
                parts = [int(part) for part in selected.versions[0].split(".")]
                parts += [0] * (4 - len(parts))
                columns = [f"COALESCE(SAFE_CAST(SPLIT_PART(ver, '.', {i}) AS BIGINT), 0)" for i in range(1, 5)]
                branches = []
                for index, part in enumerate(parts):
                    equal_prior = [f"{columns[i]} = {parts[i]}" for i in range(index)]
                    branches.append("(" + " AND ".join(equal_prior + [f"{columns[index]} > {part}"]) + ")")
                if selected.version_mode == "greater_equal":
                    branches.append("(" + " AND ".join(f"{column} = {part}" for column, part in zip(columns, parts)) + ")")
                predicates.append("AND ver RLIKE '^[0-9]+([.][0-9]+){0,3}$' AND (" + " OR ".join(branches) + ")")
            else:
                literals = ", ".join("'" + item + "'" for item in selected.versions)
                predicates.append(f"AND ver {'NOT IN' if selected.version_mode == 'exclude' else 'IN'} ({literals})")
        event_column = _identifier(event_code_column, "CID 字段")
        event_predicates = []
        for code in codes:
            if re.search(r"-\d{4}$", code):
                event_predicates.append(f"{event_column} = '{code}'")
            elif re.fullmatch(r"\d{5,7}_\d{4}", code):
                event_predicates.append(f"{event_column} = '{code.replace('_', '-')}'")
            elif "_" in code:
                event_predicates.append(f"INSTR({event_column}, '{code}') > 0")
            else:
                event_predicates.append(f"{event_column} LIKE '%{code}%'")
        values = {
            "event_predicates": " OR ".join(event_predicates),
            "value_columns": "".join(f"{name},\n        " for name in selected.value_fields),
            "outer_value_columns": "".join(f"t3.{name},\n    " for name in selected.value_fields),
            "filter_predicates": "\n      ".join(predicates),
            "source_table": _identifier(source_table, "数据表"),
            "partition_column": _identifier(partition_column, "分区字段"),
            "event_code_column": _identifier(event_code_column, "CID 字段"),
            "user_id_column": _identifier(user_id_column, "UV 字段"),
            "event_code": codes[0],
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
  cid_parm AS event_code,
  COUNT(1) AS pv,
  COUNT(DISTINCT user_id) AS uv
FROM event_detail
GROUP BY event_date, cid_parm
;
"""
