# v0.1.4 Default Value Columns Implementation Plan

**Goal:** 客户端新查询默认选中并返回 value1～value25；取消的字段不出现在明细 SQL 或 XLSX 中。

**Architecture:** 前端初始选择与后端 QueryFilters 缺省值统一为全部 25 项。显式传入的字段列表（包括空列表）保持原义，因此历史查询和 WEB 日志不会被新默认值覆盖。

**Tech Stack:** FastAPI / Pydantic、SQL 模板、原生 JavaScript、pytest、Playwright。

---

### Task 1: 后端默认字段

- 修改 `app/domain/query_filters.py`：`value_fields` 默认生成 `value1`～`value25`。
- 更新 `tests/test_query_filters.py`：空筛选条件包含全部列，显式空数组不包含任何列，WEB 仍不包含客户端列。
- 运行 `pytest tests/test_query_filters.py -q`。

### Task 2: 前端默认选中

- 修改 `app/web/index.html`：初始状态点亮全部 25 项；恢复历史查询时优先采用历史 `value_fields`，包含空数组。
- 更新前端说明文字与浏览器断言；验证取消字段后费用评估和正式查询使用相同字段集合。
- 运行浏览器回归脚本并检查桌面／窄屏布局。

### Task 3: 版本和完整回归

- 同步本地版本号与 README 至 v0.1.4。
- 运行完整 pytest、浏览器测试及 `git diff --check`。
- 仅保留本地修改，不上传 GitHub（用户本轮未要求上传）。
