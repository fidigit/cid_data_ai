import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || !process.argv[index + 1]) {
    throw new Error(`Missing required argument: ${name}`);
  }
  return process.argv[index + 1];
}

function styleHeader(range) {
  range.format = {
    fill: "#0F766E",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
}

const detailCsv = argument("--detail-csv");
const metadataFile = argument("--metadata-json");
const output = argument("--output");
const metadata = JSON.parse(await fs.readFile(metadataFile, "utf8"));
const detailCsvText = await fs.readFile(detailCsv, "utf8");

// 以 artifact-tool 作为唯一 xlsx 生成器。明细 CSV 由 Python Worker 流式生成。
const workbook = await Workbook.fromCSV(detailCsvText, { sheetName: "原始数据" });
const detailSheet = workbook.worksheets.getItem("原始数据");
detailSheet.showGridLines = false;
const detailUsedRange = detailSheet.getUsedRange(true);
if (detailUsedRange) {
  styleHeader(detailUsedRange.getRow(0));
  detailUsedRange.format.autofitColumns();
}
detailSheet.freezePanes.freezeRows(1);

const aggregationSheet = workbook.worksheets.add("聚合统计");
aggregationSheet.showGridLines = false;
aggregationSheet.getRange("A1:C1").merge();
const dayCount = Math.max(
  1,
  Math.round(
    (new Date(`${metadata.partition_end.slice(0, 4)}-${metadata.partition_end.slice(4, 6)}-${metadata.partition_end.slice(6, 8)}`)
      - new Date(`${metadata.partition_start.slice(0, 4)}-${metadata.partition_start.slice(4, 6)}-${metadata.partition_start.slice(6, 8)}`))
      / 86400000,
  ) + 1,
);
aggregationSheet.getRange("A1").values = [[`CID ${metadata.event_code} 近 ${dayCount} 天聚合统计`]];
aggregationSheet.getRange("A1:C1").format = {
  fill: "#115E59",
  font: { bold: true, color: "#FFFFFF", size: 14 },
  horizontalAlignment: "center",
};
aggregationSheet.getRange("A2:C2").values = [[
  `分区范围：${metadata.partition_start} ~ ${metadata.partition_end}`,
  "",
  "",
]];
aggregationSheet.getRange("A4:C4").values = [["日期", "PV", "UV"]];
styleHeader(aggregationSheet.getRange("A4:C4"));

const aggregationRows = metadata.aggregation.map((item) => [
  String(item.event_date ?? ""),
  Number(item.pv ?? 0),
  Number(item.uv ?? 0),
]);
if (aggregationRows.length) {
  const lastDataRow = 4 + aggregationRows.length;
  aggregationSheet.getRange(`A5:C${lastDataRow}`).values = aggregationRows;
  const totalRow = lastDataRow + 1;
  aggregationSheet.getRange(`A${totalRow}:C${totalRow}`).values = [["总计", null, null]];
  aggregationSheet.getRange(`B${totalRow}`).formulas = [[`=SUM(B5:B${lastDataRow})`]];
  aggregationSheet.getRange(`C${totalRow}`).formulas = [[`=SUM(C5:C${lastDataRow})`]];
  aggregationSheet.getRange(`A${totalRow}:C${totalRow}`).format = {
    fill: "#CCFBF1",
    font: { bold: true },
  };
  aggregationSheet.getRange(`B5:C${totalRow}`).format.numberFormat = "#,##0";
}
aggregationSheet.getRange("A:A").format.columnWidth = 18;
aggregationSheet.getRange("B:C").format.columnWidth = 14;
aggregationSheet.freezePanes.freezeRows(4);

await fs.mkdir(path.dirname(output), { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(output);
