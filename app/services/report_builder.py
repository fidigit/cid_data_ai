from __future__ import annotations

import csv
import json
import subprocess
import tempfile
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any


class ExportLimitExceeded(RuntimeError):
    pass


def _excel_safe(value: Any) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        # 防 CSV / Excel 公式注入；前导单引号在 Excel 中按文本显示。
        return "'" + value
    return value


def write_detail_csv(
    path: Path,
    *,
    columns: tuple[str, ...],
    rows: Iterable[tuple[Any, ...]],
    max_rows: int,
) -> int:
    count = 0
    with path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.writer(output)
        writer.writerow(columns)
        for row in rows:
            count += 1
            if count > max_rows:
                raise ExportLimitExceeded(
                    f"明细结果超过当前导出上限 {max_rows:,} 行；未生成不完整文件。"
                )
            writer.writerow([_excel_safe(value) for value in row])
    return count


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
    node_bin: str,
) -> int:
    """先流式写明细 CSV，再由 artifact-tool 统一生成 xlsx。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="event-export-") as tmp:
        tmp_path = Path(tmp)
        detail_csv = tmp_path / "detail.csv"
        metadata_json = tmp_path / "metadata.json"
        row_count = write_detail_csv(
            detail_csv,
            columns=detail_columns,
            rows=detail_rows,
            max_rows=max_rows,
        )
        metadata_json.write_text(
            json.dumps(
                {
                    "event_code": event_code,
                    "partition_start": partition_start,
                    "partition_end": partition_end,
                    "aggregation": aggregation,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        builder = Path(__file__).resolve().parents[2] / "scripts" / "build_report.mjs"
        result = subprocess.run(
            [
                node_bin,
                str(builder),
                "--detail-csv",
                str(detail_csv),
                "--metadata-json",
                str(metadata_json),
                "--output",
                str(destination),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"xlsx 构建失败：{result.stderr[-1500:]}")
    return row_count

