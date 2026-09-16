from __future__ import annotations

from zipfile import ZipFile

import pytest

from app.services.report_builder import build_xlsx


def _xlsx_part(path, name: str) -> str:
    with ZipFile(path) as archive:
        return archive.read(name).decode("utf-8")


def test_build_xlsx_creates_portable_two_sheet_report(tmp_path) -> None:
    destination = tmp_path / "event-report.xlsx"

    row_count = build_xlsx(
        destination=destination,
        event_code="90036",
        partition_start="20260812",
        partition_end="20260813",
        aggregation=[
            {"event_date": "20260812", "pv": 3, "uv": 2},
            {"event_date": "20260813", "pv": 5, "uv": 4},
        ],
        detail_columns=("event_date", "user_id", "value1"),
        detail_rows=[
            ("20260812", "device-1", "normal"),
            ("20260813", "device-2", "=1+1"),
        ],
        max_rows=100,
    )

    assert row_count == 2
    assert destination.is_file()

    workbook_xml = _xlsx_part(destination, "xl/workbook.xml")
    detail_xml = _xlsx_part(destination, "xl/worksheets/sheet2.xml")
    aggregation_xml = _xlsx_part(destination, "xl/worksheets/sheet1.xml")
    assert workbook_xml.index('name="聚合统计"') < workbook_xml.index('name="原始数据"')

    assert 'name="原始数据"' in workbook_xml
    assert 'name="聚合统计"' in workbook_xml
    assert "event_date" in detail_xml
    assert "device-2" in detail_xml
    assert "'=1+1" in detail_xml
    assert "CID 90036 近 2 天聚合统计" in aggregation_xml
    assert "20260812" in aggregation_xml
    assert "20260813" in aggregation_xml
    assert "<f>SUM(B5:B6)</f>" in aggregation_xml
    assert "<f>SUM(C5:C6)</f>" in aggregation_xml


def test_build_xlsx_truncates_detail_without_losing_full_statistics(tmp_path) -> None:
    destination = tmp_path / "too-large.xlsx"

    count = build_xlsx(
        destination=destination,
        event_code="90036",
        partition_start="20260813",
        partition_end="20260813",
        aggregation=[{"event_date":"20260813", "pv":2, "uv":2}],
        detail_columns=("event_date", "user_id"),
        detail_rows=[("20260813", "device-1"), ("20260813", "device-2")],
        max_rows=1,
    )

    assert destination.exists() and count == 1
    assert "只显示前1条数据" in _xlsx_part(destination, "xl/worksheets/sheet1.xml")
    assert "device-2" not in _xlsx_part(destination, "xl/worksheets/sheet2.xml")


@pytest.mark.parametrize("total", [200000, 200001])
def test_twenty_w_boundary_and_streaming(tmp_path, total):
    consumed = 0
    def rows():
        nonlocal consumed
        for index in range(total):
            consumed += 1
            yield (str(index),)
    path=tmp_path / "boundary.xlsx"
    count=build_xlsx(destination=path,event_code="90036",partition_start="20260901",partition_end="20260901",aggregation=[{"event_date":"20260901","pv":total,"uv":total}],detail_columns=("uid",),detail_rows=rows(),max_rows=200000)
    assert count == consumed == 200000
    summary=_xlsx_part(path,"xl/worksheets/sheet1.xml")
    assert ("只显示前20w条数据" in summary) == (total>200000)
    assert f"<v>{total}</v>" in summary
    detail=_xlsx_part(path,"xl/worksheets/sheet2.xml")
    assert detail.count("<row ") == 200001  # header + detail
