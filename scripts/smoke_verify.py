from __future__ import annotations

from pathlib import Path

from app.domain.event_codes import extract_unique_event_code
from app.domain.partitions import PartitionRange
from app.infrastructure.sql_renderer import EventQueryRenderer
from app.services.cost_estimates import (
    CostEstimateTokenError,
    issue_cost_estimate_token,
    verify_cost_estimate_token,
)


def main() -> None:
    from app.api.routes import router

    route_paths = {route.path for route in router.routes}
    assert "/api/v1/query-estimates" in route_paths
    assert "/api/v1/query-requests" in route_paths

    assert extract_unique_event_code("看看90056_0001数据") == "90056_0001"
    assert extract_unique_event_code("查询 160036-0003") == "160036-0003"
    assert extract_unique_event_code("查询 140961") == "140961"

    renderer = EventQueryRenderer(Path("sql/event_detail.sql"))
    sql = renderer.render_detail(
        source_table="biugolite_dwv_event_detail_mob_fdt",
        partition_column="dt",
        event_code_column="cid_parm",
        user_id_column="uid",
        event_code="90056_0001",
        partitions=PartitionRange(start="20260805", end="20260811"),
    )
    assert "dt >= '20260805'" in sql
    assert "dt <= '20260811'" in sql
    assert "REPLACE('90056_0001', '-', '_')" in sql
    assert "uid AS user_id" in sql
    assert "COUNT(DISTINCT user_id) AS uv" in renderer.render_daily_aggregation(sql)

    claims = {
        "secret": "smoke-test-secret",
        "requester_id": "dev-user",
        "event_code": "90056_0001",
        "partition_start": "20260805",
        "partition_end": "20260811",
    }
    token, _ = issue_cost_estimate_token(
        **claims, estimated_amount_cny=1.25, ttl_seconds=600, now=1000
    )
    verify_cost_estimate_token(token, **claims, now=1001)
    try:
        verify_cost_estimate_token(token, **(claims | {"event_code": "90056_0002"}), now=1001)
    except CostEstimateTokenError:
        pass
    else:
        raise AssertionError("changed CID must invalidate the cost estimate token")

    print("smoke-verification-ok")


if __name__ == "__main__":
    main()
