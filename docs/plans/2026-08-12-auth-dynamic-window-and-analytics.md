# Auth, Dynamic Window, Export Analytics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不改变现有查询终端视觉基线的前提下，增加安全登录、超级管理员使用统计、默认 1 天且可选 1–7 天的查询窗口、XLSX 导出和页面内 dt/PV/UV 报表。

**Architecture:** 保持 FastAPI + SQLAlchemy + Celery/开发线程执行的模块化单体。身份使用签名 HttpOnly Cookie，审计数据写入独立表；费用凭证绑定账号、CID、分区和估算金额；导出任务把聚合数据同时写入数据库和 XLSX，前端用原生 SVG 展示。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy、PyODPS、Celery、SQLite/PostgreSQL、原生 HTML/CSS/JavaScript、`@oai/artifact-tool`。

---

### Task 1: 动态分区与费用凭证

**Files:**
- Modify: `app/domain/partitions.py`
- Modify: `app/api/schemas.py`
- Modify: `app/api/routes.py`
- Modify: `app/services/cost_estimates.py`
- Test: `tests/test_partitions.py`
- Test: `tests/test_cost_estimates.py`
- Test: `tests/test_query_estimate_api.py`

**Steps:**
1. 为 1–7 天窗口编写失败测试，确认默认 1 天和越界拒绝。
2. 实现 `latest_calendar_days(today, fmt, days)`，请求模型增加 `days=1`。
3. 将分区和估算金额绑定进签名费用凭证，提交时验证同一窗口。
4. 运行相关测试，预期全部通过。

### Task 2: 登录鉴权与超级管理员

**Files:**
- Create: `app/services/auth.py`
- Create: `app/api/auth_routes.py`
- Modify: `app/models.py`
- Modify: `app/core/config.py`
- Modify: `app/main.py`
- Modify: `.env.example`
- Test: `tests/test_auth.py`

**Steps:**
1. 编写密码哈希、会话篡改、过期和角色拒绝测试。
2. 使用 scrypt 存储密码哈希，HMAC 签名会话 Cookie。
3. 启动时从环境配置初始化超级管理员，不在源码保存密码。
4. 实现登录、退出、当前用户接口以及管理员依赖。
5. 运行鉴权测试。

### Task 3: 使用统计与管理员 API

**Files:**
- Create: `app/services/usage_stats.py`
- Create: `app/api/usage_routes.py`
- Modify: `app/models.py`
- Modify: `app/api/routes.py`
- Test: `tests/test_usage_stats.py`

**Steps:**
1. 编写访问次数、停留秒数、费用评估、导出和金额汇总测试。
2. 新增访问会话和使用事件表。
3. 实现访问开始、心跳、结束与管理员聚合接口。
4. 在费用评估成功和导出受理时写入审计事件。
5. 验证普通成员无法访问管理员统计。

### Task 4: 查询上下文、聚合数据与 XLSX

**Files:**
- Modify: `app/models.py`
- Modify: `app/services/query_jobs.py`
- Modify: `app/workers/tasks.py`
- Modify: `app/api/schemas.py`
- Modify: `scripts/build_report.mjs`
- Test: `tests/test_query_jobs.py`

**Steps:**
1. 新增独立查询上下文表保存分区和估算金额，避免依赖任务执行时的当前日期。
2. 新增按日聚合表，Worker 写入 event_date、PV、UV。
3. 任务状态接口在成功后返回聚合数组，下载接口继续返回 XLSX。
4. 把 XLSX 标题从固定近 7 天改为实际分区范围，并保留“原始数据/聚合统计”工作表。
5. 使用测试数据生成、检查和渲染 XLSX。

### Task 5: 保留视觉基线的前端增量改造

**Files:**
- Modify: `app/web/index.html`
- Create: `app/web/admin.html`
- Test: `scripts/check_frontend.cjs`

**Steps:**
1. 在同一视觉系统中增加登录遮罩，主界面默认不可见。
2. 在输入区旁增加 1–7 天选择器，默认 1 天；修改后使费用凭证失效。
3. 将第二阶段按钮语义改为导出，成功后自动提供 XLSX 下载。
4. 在页面下方增加原生 SVG PV/UV 趋势图和精确值表格。
5. 新建同风格管理员统计页，展示人员汇总和最近访问时间。
6. 运行前端语法检查并进行浏览器视觉验收。

### Task 6: 全链路验证

**Files:**
- Modify: `README.md`
- Modify: `history_PRE/ask.md`
- Modify: `history_PRE/thinking.md`

**Steps:**
1. 运行完整 pytest。
2. 启动服务，验证未登录、登录、1 天评估、窗口变更失效、管理员权限和统计页。
3. 使用受控测试数据验证 XLSX 两个工作表和 PV/UV 报表。
4. 记录配置方法、安全边界和生产部署注意事项。

