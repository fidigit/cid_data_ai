from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import JobStatus


class QueryRequest(BaseModel):
    log_type: Literal["client", "web"] = "client"
    question: str = Field(min_length=1, max_length=1000)
    start_date: date | None = None
    end_date: date | None = None
    days: int = Field(default=1, ge=1, le=7, exclude=True)
    estimate_token: str = Field(min_length=1, max_length=4096)


class QueryEstimateRequest(BaseModel):
    log_type: Literal["client", "web"] = "client"
    question: str = Field(min_length=1, max_length=1000)
    start_date: date | None = None
    end_date: date | None = None
    days: int = Field(default=1, ge=1, le=7)


class QueryEstimateResponse(BaseModel):
    log_type: Literal["client", "web"] = "client"
    event_code: str
    days: int
    partition_start: str
    partition_end: str
    input_size_bytes: int
    input_size_gib: float
    complexity: float
    udf_count: int
    estimated_amount_cny: float
    price_per_gib_cny: float
    expires_at: datetime
    estimate_token: str


class JobResponse(BaseModel):
    log_type: Literal["client", "web"] = "client"
    id: str
    status: JobStatus
    event_code: str
    created_at: datetime | None
    detail_row_count: int | None = None
    error_message: str | None = None
    aggregation: list["DailyAggregationResponse"] = Field(default_factory=list)


class DailyAggregationResponse(BaseModel):
    event_date: str
    pv: int
    uv: int
