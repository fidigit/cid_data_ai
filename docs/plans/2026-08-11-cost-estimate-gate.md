# Cost Estimate Gate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让用户在网页端完成 ODPS 查询费用评估后，才可提交同一 CID 和日期范围的真实导出任务。

**Architecture:** API 渲染固定 SQL 后调用 PyODPS `execute_sql_cost`；结果通过带签名、短时有效且绑定用户/CID/日期范围的确认令牌返回。真实查询接口验证令牌，禁止绕过估价直接入队。

**Tech Stack:** FastAPI、PyODPS、Python 标准库 HMAC、原生 HTML/CSS/JavaScript。

---

### Task 1: 费用估价与确认令牌

**Files:**
- Create: `app/services/cost_estimates.py`
- Modify: `app/infrastructure/odps_gateway.py`
- Test: `tests/test_cost_estimates.py`

**Step 1:** 先写令牌签发、验证及过期测试。

**Step 2:** 实现 `execute_sql_cost` 适配和输入量/复杂度换算。

**Step 3:** 运行 `pytest tests/test_cost_estimates.py -v`。

### Task 2: API 查询前置校验

**Files:**
- Modify: `app/api/schemas.py`
- Modify: `app/api/routes.py`
- Modify: `app/core/config.py`
- Modify: `app/domain/event_codes.py`
- Modify: `app/infrastructure/sql_renderer.py`
- Test: `tests/test_cost_estimates.py`

**Step 1:** 新增 `/api/v1/query-estimates`，返回估价和确认令牌。

**Step 2:** 修改 `/api/v1/query-requests`，要求令牌与当前用户、CID、近 7 天分区一致。

**Step 3:** 支持纯数字、连字符和下划线 CID，并允许 `WITH` 明细 SQL 被聚合包装。

### Task 3: 费用评估控制台

**Files:**
- Modify: `app/web/index.html`

**Step 1:** 默认只启用“费用评估”，输入变化后清除旧估价。

**Step 2:** 展示扫描量、复杂度、UDF 数、粗估金额与有效时间。

**Step 3:** 仅在估价成功时启用“提交查询”；提交后继续轮询原有任务状态。

### Task 4: 验证

**Files:**
- Test: `tests/test_cost_estimates.py`

**Step 1:** 运行 Python 编译检查与单元测试。

**Step 2:** 启动本地服务，检查空输入、估价失败、估价成功、令牌过期和真实提交的页面状态。

