from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class PartitionRange:
    start: str
    end: str


def latest_calendar_days(today: date, fmt: str, days: int = 1) -> PartitionRange:
    """返回截至昨天的最近 N 个完整自然日，N 只允许 1 至 7。"""
    if not 1 <= days <= 7:
        raise ValueError("查询时间长度必须在 1 到 7 天之间。")
    end = today - timedelta(days=1)
    return PartitionRange(
        start=(end - timedelta(days=days - 1)).strftime(fmt),
        end=end.strftime(fmt),
    )


def calendar_date_range(
    *, today: date, start_date: date, end_date: date, fmt: str
) -> PartitionRange:
    """校验并格式化用户选择的完整自然日范围。"""
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期。")
    if end_date >= today:
        raise ValueError("不能选择今天及以后的日期。")
    days = (end_date - start_date).days + 1
    if days > 7:
        raise ValueError("查询时间区间最长为 7 天。")
    return PartitionRange(start=start_date.strftime(fmt), end=end_date.strftime(fmt))


def latest_seven_calendar_days(today: date, fmt: str) -> PartitionRange:
    """兼容旧调用；返回截至昨天的最近七个完整自然日。"""
    return latest_calendar_days(today, fmt, 7)
