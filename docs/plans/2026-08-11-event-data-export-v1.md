# Event Data Export V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建一个能从企业微信或网页接收 CID 查询、异步查询 ODPS、导出含聚合统计的 xlsx、并记录审计的 V1 工具。

**Architecture:** FastAPI 创建并展示任务；Celery Worker 执行固定模板 SQL 和 xlsx 构建；PostgreSQL 保存任务/下载审计，Redis 负责排队。ODPS 和企业微信均放在可替换的基础设施适配层。

**Tech Stack:** Python 3.11、FastAPI、Celery、Redis、PostgreSQL、PyODPS、Node.js、@oai/artifact-tool、Docker Compose。

---

### Task 1: 固化 V1 输入与 CID 规则

**Files:**
- Create: `app/domain/event_codes.py`
- Create: `tests/test_event_codes.py`

**Step 1: Write the failing test**

```python
def test_extracts_one_event_code_from_natural_language():
    assert extract_unique_event_code("帮我查询 10002_0003 最近 7 天") == "10002_0003"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_event_codes.py -v`

**Step 3: Write minimal implementation**

实现边界安全的 CID 正则；无编码或多编码抛出用户可读错误。

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_event_codes.py -v`

**Step 5: Commit**

```bash
git add app/domain/event_codes.py tests/test_event_codes.py
git commit -m "feat: parse a unique event code"
```

### Task 2: 固定 SQL 模板与 ODPS 适配层

**Files:**
- Create: `sql/event_detail.sql`
- Create: `app/infrastructure/sql_renderer.py`
- Create: `app/infrastructure/odps_gateway.py`
- Test: `tests/test_sql_renderer.py`

**Step 1: Write the failing test**

测试模板只接受合法 CID、管理员配置的标识符，聚合 SQL 从同一明细 CTE 计算日期/PV/UV。

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_sql_renderer.py -v`

**Step 3: Write minimal implementation**

渲染固定明细 SQL；在 ODPS 内聚合；PyODPS 使用异步 SQL 和 InstanceTunnel。

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_sql_renderer.py -v`

**Step 5: Commit**

```bash
git add sql app/infrastructure tests/test_sql_renderer.py
git commit -m "feat: add safe ODPS query templates"
```

### Task 3: 任务、审计与异步 Worker

**Files:**
- Create: `app/models.py`
- Create: `app/database.py`
- Create: `app/services/query_jobs.py`
- Create: `app/workers/tasks.py`
- Test: `tests/test_query_jobs.py`

**Step 1: Write the failing test**

测试任务创建时记录账号、来源、请求 IP；下载时建立独立日志。

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_query_jobs.py -v`

**Step 3: Write minimal implementation**

建立状态机 `queued → running → succeeded|failed`，Worker 按 `job_id` 幂等执行。

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_query_jobs.py -v`

**Step 5: Commit**

```bash
git add app tests/test_query_jobs.py
git commit -m "feat: add query job audit trail"
```

### Task 4: xlsx 生成与渠道回执

**Files:**
- Create: `scripts/build_report.mjs`
- Create: `app/services/report_builder.py`
- Create: `app/infrastructure/wecom.py`
- Test: `tests/test_report_builder.py`

**Step 1: Write the failing test**

使用两行明细和两天聚合生成工作簿，断言存在 `原始数据`、`聚合统计`，并检查统计值。

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_builder.py -v`

**Step 3: Write minimal implementation**

使用 `@oai/artifact-tool` 生成 xlsx；大于允许行数时失败而非截断；企业微信采用文件上传或短期安全链接适配接口。

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_builder.py -v`

**Step 5: Commit**

```bash
git add scripts app tests/test_report_builder.py
git commit -m "feat: export audited event report workbook"
```

### Task 5: API、网页、部署和验收

**Files:**
- Create: `app/main.py`
- Create: `app/api/routes.py`
- Create: `app/web/index.html`
- Create: `docker-compose.yml`
- Create: `Dockerfile`
- Create: `docs/runbook/development-and-deployment.md`

**Step 1: Write the failing test**

测试 `/healthz` 和任务提交 API 对无效 CID 的 422 响应。

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`

**Step 3: Write minimal implementation**

暴露 API、最小网页和健康检查；写入企业微信回调配置、迁移、反向代理、监控和回滚手册。

**Step 4: Run test to verify it passes**

Run: `pytest -q`

**Step 5: Commit**

```bash
git add app docker-compose.yml Dockerfile docs
git commit -m "feat: expose event export service"
```

