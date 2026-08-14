from __future__ import annotations

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings


@dataclass(frozen=True)
class QueryStream:
    columns: tuple[str, ...]
    rows: Iterable[tuple[Any, ...]]
    instance_id: str | None


@dataclass(frozen=True)
class QueryCost:
    input_size_bytes: int
    complexity: float
    udf_count: int


class OdpsGateway:
    """PyODPS 适配层；统计应始终在 ODPS 中执行，不在 Worker 内用 pandas 聚合。"""

    def __init__(self, settings: Settings) -> None:
        settings.validate_odps_ready()
        self.settings = settings

    def _client(self):
        from odps import ODPS

        return ODPS(
            access_id=self.settings.odps_access_id,
            secret_access_key=self.settings.odps_access_key_secret,
            project=self.settings.odps_project,
            endpoint=self.settings.odps_endpoint,
            tunnel_endpoint=self.settings.odps_tunnel_endpoint or None,
        )

    def estimate_sql_cost(self, sql: str) -> QueryCost:
        """执行 MaxCompute COST SQL，不运行明细查询。"""
        cost = self._client().execute_sql_cost(sql)
        return QueryCost(
            input_size_bytes=int(getattr(cost, "input_size", 0) or 0),
            complexity=float(getattr(cost, "complexity", 0) or 0),
            udf_count=int(getattr(cost, "udf_num", 0) or 0),
        )

    @contextmanager
    def open_rows(self, sql: str) -> Generator[QueryStream, None, None]:
        client = self._client()
        instance = client.run_sql(sql)
        instance.wait_for_success()
        with instance.open_reader(tunnel=True, limit=False) as reader:
            columns = tuple(column.name for column in reader.schema.columns)

            def iterator() -> Generator[tuple[Any, ...], None, None]:
                for record in reader:
                    yield tuple(record[name] for name in columns)

            yield QueryStream(
                columns=columns,
                rows=iterator(),
                instance_id=getattr(instance, "id", None),
            )
