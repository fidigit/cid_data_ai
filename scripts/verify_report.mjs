import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [input, previewDir] = process.argv.slice(2);
if (!input || !previewDir) {
  throw new Error("Usage: verify_report.mjs <xlsx> <preview-dir>");
}

const file = await FileBlob.load(input);
const workbook = await SpreadsheetFile.importXlsx(file);
const sheets = await workbook.inspect({ kind: "sheet", include: "id,name" });
const aggregate = await workbook.inspect({
  kind: "table",
  sheetId: "聚合统计",
  range: "A1:C12",
  tableMaxRows: 12,
  tableMaxCols: 3,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 20 },
});
await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["原始数据", "聚合统计"]) {
  const image = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(`${previewDir}/${sheetName}.png`, new Uint8Array(await image.arrayBuffer()));
}
console.log(JSON.stringify({ sheets: sheets.ndjson, aggregate: aggregate.ndjson, errors: errors.ndjson }));

