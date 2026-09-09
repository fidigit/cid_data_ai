from __future__ import annotations

import tempfile
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import xlsxwriter


class ExportLimitExceeded(RuntimeError):
    pass


def _excel_safe(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        # 即使工作簿已关闭自动公式识别，也保留显式文本前缀以防后续处理链误判。
        return "'" + value
    return value


def _day_count(partition_start: str, partition_end: str) -> int:
    start = datetime.strptime(partition_start, "%Y%m%d").date()
    end = datetime.strptime(partition_end, "%Y%m%d").date()
    return (end - start).days + 1


def _write_detail_sheet(
    workbook: xlsxwriter.Workbook,
    *,
    columns: tuple[str, ...],
    rows: Iterable[tuple[Any, ...]],
    max_rows: int,
) -> int:
    worksheet = workbook.add_worksheet("原始数据")
    worksheet.hide_gridlines(2)
    worksheet.freeze_panes(1, 0)

    header_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#0F766E",
            "align": "center",
            "valign": "vcenter",
            "bottom": 1,
            "bottom_color": "#115E59",
        }
    )
    worksheet.set_row(0, 23)
    for column_index, column_name in enumerate(columns):
        worksheet.write(0, column_index, column_name, header_format)

    widths = [max(12, len(str(column_name)) + 2) for column_name in columns]
    count = 0
    for row in rows:
        count += 1
        if count > max_rows:
            raise ExportLimitExceeded(
                f"明细结果超过当前导出上限 {max_rows:,} 行；未生成不完整文件。"
            )
        if len(row) != len(columns):
            raise RuntimeError("ODPS 明细列数与表头列数不一致，已停止生成 XLSX。")
        for column_index, value in enumerate(row):
            safe_value = _excel_safe(value)
            worksheet.write(count, column_index, safe_value)
            widths[column_index] = min(48, max(widths[column_index], len(str(safe_value)) + 2))

    for column_index, width in enumerate(widths):
        worksheet.set_column(column_index, column_index, width)
    if columns:
        worksheet.autofilter(0, 0, count, len(columns) - 1)
    return count


def _write_aggregation_sheet(
    workbook: xlsxwriter.Workbook,
    *,
    event_code: str,
    partition_start: str,
    partition_end: str,
    aggregation: list[dict[str, Any]],
    log_type: str = "client",
) -> None:
    worksheet = workbook.add_worksheet("聚合统计")
    worksheet.hide_gridlines(2)
    worksheet.freeze_panes(4, 0)
    worksheet.set_column("A:A", 18)
    worksheet.set_column("B:C", 14)

    title_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "font_size": 14,
            "bg_color": "#115E59",
            "align": "center_across",
            "valign": "vcenter",
        }
    )
    subtitle_format = workbook.add_format(
        {"font_color": "#475569", "bg_color": "#F0FDFA", "align": "left"}
    )
    header_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#0F766E",
            "align": "center",
            "valign": "vcenter",
            "bottom": 1,
            "bottom_color": "#115E59",
        }
    )
    count_format = workbook.add_format({"num_format": "#,##0", "align": "right"})
    total_label_format = workbook.add_format(
        {"bold": True, "bg_color": "#CCFBF1", "top": 1, "top_color": "#5EEAD4"}
    )
    total_count_format = workbook.add_format(
        {
            "bold": True,
            "bg_color": "#CCFBF1",
            "num_format": "#,##0",
            "align": "right",
            "top": 1,
            "top_color": "#5EEAD4",
        }
    )

    worksheet.set_row(0, 26)
    label = "WEB eventid" if log_type == "web" else "CID"
    title = f"{label} {event_code} 近 {_day_count(partition_start, partition_end)} 天聚合统计"
    worksheet.write(0, 0, title, title_format)
    worksheet.write_blank(0, 1, None, title_format)
    worksheet.write_blank(0, 2, None, title_format)
    worksheet.write(1, 0, f"分区范围：{partition_start} ~ {partition_end}", subtitle_format)
    worksheet.write_blank(1, 1, None, subtitle_format)
    worksheet.write_blank(1, 2, None, subtitle_format)
    worksheet.set_row(3, 22)
    worksheet.write_row(3, 0, ["日期", "PV", "UV"], header_format)
    if log_type == "web":
        worksheet.set_column("D:D", 18)
        worksheet.write(3, 3, "eventid", header_format)

    total_pv = 0
    total_uv = 0
    for offset, item in enumerate(aggregation):
        row_index = 4 + offset
        pv = int(item.get("pv") or 0)
        uv = int(item.get("uv") or 0)
        total_pv += pv
        total_uv += uv
        worksheet.write(row_index, 0, str(item.get("event_date") or ""))
        worksheet.write_number(row_index, 1, pv, count_format)
        worksheet.write_number(row_index, 2, uv, count_format)
        if log_type == "web":
            worksheet.write_string(row_index, 3, event_code)

    if aggregation:
        total_row = 4 + len(aggregation)
        last_data_excel_row = 4 + len(aggregation)
        worksheet.write(total_row, 0, "每日合计", total_label_format)
        worksheet.write_formula(
            total_row,
            1,
            f"=SUM(B5:B{last_data_excel_row})",
            total_count_format,
            total_pv,
        )
        worksheet.write_formula(
            total_row,
            2,
            f"=SUM(C5:C{last_data_excel_row})",
            total_count_format,
            total_uv,
        )
        worksheet.write(total_row + 2, 0, "UV合计为每日UV之和，非区间去重人数。")


def build_xlsx(
    *,
    destination: Path,
    event_code: str,
    partition_start: str,
    partition_end: str,
    aggregation: list[dict[str, Any]],
    detail_columns: tuple[str, ...],
    detail_rows: Iterable[tuple[Any, ...]],
    max_rows: int,
    log_type: str = "client",
) -> int:
    """使用 XlsxWriter 流式生成可跨平台部署的双 Sheet 工作簿。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="event-export-", dir=destination.parent) as tmp:
        tmp_path = Path(tmp)
        temporary_output = tmp_path / destination.name
        with xlsxwriter.Workbook(
            temporary_output,
            {
                "constant_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
                "tmpdir": str(tmp_path),
            },
        ) as workbook:
            workbook.use_zip64()
            workbook.set_properties(
                {
                    "title": f"{log_type} {event_code} 数据导出",
                    "subject": f"{partition_start} 至 {partition_end} 埋点明细与聚合统计",
                    "author": "CID Data AI",
                }
            )
            row_count = _write_detail_sheet(
                workbook,
                columns=detail_columns,
                rows=detail_rows,
                max_rows=max_rows,
            )
            _write_aggregation_sheet(
                workbook,
                event_code=event_code,
                partition_start=partition_start,
                partition_end=partition_end,
                aggregation=aggregation,
                log_type=log_type,
            )
        temporary_output.replace(destination)
    return row_count
