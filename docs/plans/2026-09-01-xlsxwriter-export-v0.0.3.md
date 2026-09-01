# XlsxWriter Export v0.0.3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the private Node-based XLSX runtime with a public, cross-platform, memory-conscious XlsxWriter implementation and publish v0.0.3.

**Architecture:** The worker will continue streaming ODPS rows into `build_xlsx`, but Python will write them directly into a temporary XLSX using XlsxWriter `constant_memory`. The completed file will atomically replace the destination only after the workbook closes successfully. The workbook contract remains two sheets: `原始数据` and `聚合统计`.

**Tech Stack:** Python 3.11+, XlsxWriter, pytest, ZIP/XML workbook assertions, Git/GitHub.

---

### Task 1: Add failing workbook contract tests

**Files:**
- Create: `tests/test_report_builder.py`

**Steps:**
1. Test that `build_xlsx` creates both required sheets, detail values, PV/UV rows, and total formulas without a Node argument.
2. Test that formula-like detail strings remain text.
3. Test that exceeding the row limit raises `ExportLimitExceeded` and leaves no destination file.
4. Run the focused test and confirm it fails against the v0.0.2 API.

### Task 2: Implement streaming XlsxWriter export

**Files:**
- Modify: `app/services/report_builder.py`
- Modify: `app/workers/tasks.py`
- Modify: `pyproject.toml`

**Steps:**
1. Add `XlsxWriter>=3.2,<4` as a runtime dependency.
2. Replace temporary CSV, metadata JSON, and Node subprocess execution with direct Python workbook creation.
3. Enable constant-memory mode and disable automatic string-to-formula/URL conversion.
4. Preserve the two-sheet names, formatting, freeze panes, PV/UV totals, row limit, and formula-injection protection.
5. Build in a destination-local temporary directory and move the file only after successful close.
6. Run the focused tests until they pass.

### Task 3: Remove obsolete Node export runtime

**Files:**
- Delete: `scripts/build_report.mjs`
- Delete: `scripts/verify_report.mjs`
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `docs/runbook/development-and-deployment.md`

**Steps:**
1. Remove `SPREADSHEET_NODE_BIN` and the worker argument.
2. Remove Node installation and `node_modules` deployment mounts used only by XLSX export.
3. Update the runbook to document pure-Python installation and workbook verification.
4. Search the active code and deployment documentation to confirm no private artifact runtime remains.

### Task 4: Version, regression, and workbook verification

**Files:**
- Modify: `app/main.py`
- Modify: `README.md`
- Modify: `pyproject.toml`

**Steps:**
1. Set the application version to `0.0.3` and document the portable exporter.
2. Generate a representative workbook from sanitized fixture data.
3. Inspect workbook ZIP/XML structure, values, formulas, and sheet names.
4. Run frontend validation and the complete pytest suite.
5. Run `git diff --check` and a sensitive-file audit.

### Task 5: Publish v0.0.3

**Steps:**
1. Stage only reviewed source, tests, documentation, and dependency changes.
2. Commit as `release: v0.0.3`.
3. Create annotated tag `v0.0.3`.
4. Atomically push `main` and `v0.0.3` to `fidigit/cid_data_ai`.
5. Verify remote refs and provide safe target-machine update commands that preserve `.env` and `data/app.db`.
