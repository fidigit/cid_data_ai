import pytest

from app.domain.event_codes import (
    EventCodeExtractionError,
    extract_unique_event_code,
    find_event_codes,
    is_valid_event_code,
)


@pytest.mark.parametrize(
    "question, expected",
    [
        ("我需要查询10001_0001埋点", "10001_0001"),
        ("帮我查询 10002_0003 最近 7 天的数据", "10002_0003"),
        ("10003_0002帮我看一下.....", "10003_0002"),
        ("看看90056_0001数据", "90056_0001"),
        ("帮我查询 160036-0003", "160036-0003"),
        ("查询事件 140961", "140961"),
    ],
)
def test_extracts_one_event_code_from_natural_language(question: str, expected: str) -> None:
    assert extract_unique_event_code(question) == expected


def test_rejects_multiple_event_codes() -> None:
    with pytest.raises(EventCodeExtractionError, match="多个 CID"):
        extract_unique_event_code("比较 10001_0001 和 10002_0003")


def test_deduplicates_same_event_code() -> None:
    assert find_event_codes("10001_0001 10001_0001") == ["10001_0001"]


def test_ignores_whitespace_inside_event_code() -> None:
    assert extract_unique_event_code("看看 1700930 _ 0001 数据") == "1700930_0001"


def test_extracts_seven_digit_event_code() -> None:
    assert extract_unique_event_code("看看1700930数据") == "1700930"


def test_extracts_seven_digit_event_code_with_suffix() -> None:
    assert extract_unique_event_code("看看1700930_0001数据") == "1700930_0001"
    assert is_valid_event_code("1700930_0001")


@pytest.mark.parametrize("value", ["12345678", "1700930_001"])
def test_rejects_out_of_range_event_code_formats(value: str) -> None:
    assert not is_valid_event_code(value)
