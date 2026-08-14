from datetime import date

import pytest

from app.domain.partitions import calendar_date_range, latest_calendar_days, latest_seven_calendar_days


def test_latest_calendar_days_defaults_to_yesterday_only() -> None:
    actual = latest_calendar_days(date(2026, 8, 11), "%Y%m%d")
    assert actual.start == "20260810"
    assert actual.end == "20260810"


def test_latest_calendar_days_accepts_up_to_seven_days() -> None:
    actual = latest_calendar_days(date(2026, 8, 11), "%Y%m%d", 7)
    assert actual.start == "20260804"
    assert actual.end == "20260810"


@pytest.mark.parametrize("days", [0, 8])
def test_latest_calendar_days_rejects_out_of_range(days: int) -> None:
    with pytest.raises(ValueError, match="1 到 7 天"):
        latest_calendar_days(date(2026, 8, 11), "%Y%m%d", days)


def test_latest_seven_calendar_days_excludes_today() -> None:
    actual = latest_seven_calendar_days(date(2026, 8, 11), "%Y%m%d")
    assert actual.start == "20260804"
    assert actual.end == "20260810"


def test_explicit_calendar_range_accepts_up_to_seven_complete_days() -> None:
    actual = calendar_date_range(
        today=date(2026, 8, 11),
        start_date=date(2026, 8, 4),
        end_date=date(2026, 8, 10),
        fmt="%Y%m%d",
    )
    assert (actual.start, actual.end) == ("20260804", "20260810")


@pytest.mark.parametrize(
    "start,end,message",
    [
        (date(2026, 8, 10), date(2026, 8, 11), "今天及以后"),
        (date(2026, 8, 3), date(2026, 8, 10), "最长为 7 天"),
        (date(2026, 8, 10), date(2026, 8, 9), "开始日期"),
    ],
)
def test_explicit_calendar_range_rejects_invalid_dates(start: date, end: date, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        calendar_date_range(today=date(2026, 8, 11), start_date=start, end_date=end, fmt="%Y%m%d")
