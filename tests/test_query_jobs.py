from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import QueryJobContext
from app.services.query_jobs import create_job, get_daily_aggregation, replace_daily_aggregation


def test_job_keeps_original_partition_and_daily_aggregation() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        job = create_job(
            db,
            source="web",
            requester_id="member01",
            requester_name="成员一",
            requester_ip="127.0.0.1",
            raw_question="看看90056_0001数据",
            event_code="90056_0001",
            partition_start="20260810",
            partition_end="20260812",
            days=3,
            estimated_amount_cny=2.5,
        )
        context = db.get(QueryJobContext, job.id)
        assert context is not None
        assert context.days == 3
        assert context.partition_start == "20260810"
        assert context.estimated_amount_cny == 2.5

        replace_daily_aggregation(
            db,
            job_id=job.id,
            rows=[
                {"event_date": "20260810", "pv": 12, "uv": 8},
                {"event_date": "20260811", "pv": 20, "uv": 13},
            ],
        )
        rows = get_daily_aggregation(db, job.id)
        assert [(item.event_date, item.pv, item.uv) for item in rows] == [
            ("20260810", 12, 8),
            ("20260811", 20, 13),
        ]
