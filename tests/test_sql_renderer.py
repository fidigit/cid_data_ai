from pathlib import Path

import pytest

from app.domain.partitions import PartitionRange
from app.infrastructure.sql_renderer import EventQueryRenderer, SqlTemplateError


def test_renders_admin_controlled_template() -> None:
    renderer = EventQueryRenderer(Path("sql/event_detail.sql"))
    sql = renderer.render_detail(
        source_table="app_log.events",
        partition_column="ds",
        event_code_column="cid",
        user_id_column="device_id",
        event_code="10001_0001",
        partitions=PartitionRange(start="20260805", end="20260811"),
    )
    assert "FROM app_log.events" in sql
    assert "REPLACE(cid, '-', '_')" in sql
    assert "REPLACE('10001_0001', '-', '_')" in sql
    assert "ds >= '20260805'" in sql
    assert "ds <= '20260811'" in sql
    assert "device_id AS uid" in sql
    assert "$" not in sql


def test_rejects_invalid_configured_identifier() -> None:
    renderer = EventQueryRenderer(Path("sql/event_detail.sql"))
    with pytest.raises(SqlTemplateError, match="数据表"):
        renderer.render_detail(
            source_table="events; DROP TABLE events",
            partition_column="ds",
            event_code_column="cid",
            user_id_column="device_id",
            event_code="10001_0001",
            partitions=PartitionRange(start="20260805", end="20260811"),
        )


def test_aggregation_uses_detail_aliases() -> None:
    sql = EventQueryRenderer.render_daily_aggregation("SELECT ds AS event_date, uid AS user_id FROM t")
    assert "COUNT(DISTINCT user_id) AS uv" in sql
    assert "GROUP BY event_date" in sql
    assert "ORDER BY" not in sql
