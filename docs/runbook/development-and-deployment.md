# 开发、部署与验收手册

## 1. 凭证与配置

- 不在 `.env`、SQL、日志、Git 历史或企业微信群发送 AccessKey；`.env` 仅供本机测试。
- 生产从密钥服务注入短期 STS/RAM 凭证；授权仅限必要的 MaxCompute Project、固定源表和 Tunnel 下载。
- 设置 `DATA_SOURCE_TABLE`、字段名和 `sql/event_detail.sql` 后，先在低权限测试账号跑一条已知 CID。
- 企业微信上线前必须确定“智能机器人 API 模式”或“自建应用”，配置 HTTPS 回调、Token、EncodingAESKey、可信 IP，并以官方 SDK/协议验签与解密。普通群机器人 Webhook 只能作为通知出口。

## 2. xlsx 运行时

项目使用公开的 Python `XlsxWriter` 生成工作簿，并启用 `constant_memory` 按行流式写入明细。API 与 Worker 不再依赖 Node.js、Codex 运行时或私有 npm 包。`XlsxWriter` 已声明在 `pyproject.toml`，执行常规 Python 安装即可获得完整导出能力。

在本机执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest -q
```

Linux 或 macOS 使用：

```bash
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m pytest -q
```

### Windows 现有部署升级（保留账号与密码）

账号、密码哈希和使用统计位于被 Git 忽略的 `data/app.db`，真实配置位于被 Git 忽略的 `.env`。升级前停止服务并做时间戳备份，然后只快进更新已跟踪代码：

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item .env ".env.backup-$stamp"
Copy-Item data\app.db "data\app.db.backup-$stamp"
git status --short
git fetch origin --tags
git switch main
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe .\scripts\manage_users.py list
```

如果 `git status --short` 显示 `.env` 或 `data/app.db`，说明本机 `.gitignore` 状态异常，应停止升级并先排查；正常情况下它们不会出现在输出中，也不会被 `git pull` 覆盖。

## 3. 发布流程

1. 在 CI 跑 `pytest -q`；`tests/test_report_builder.py` 会用脱敏数据生成 XLSX，并检查两个 Sheet、明细文本安全、PV/UV 汇总值、公式以及超限时不发布半成品文件。
2. 构建 API/Worker 同一版本镜像，在预发布环境运行迁移、健康检查和一个测试 CID。
3. Nginx 配置 HTTPS、访问日志、请求大小/超时限制；仅信任自身写入的身份与真实 IP 头。
4. 部署至少两个 API 副本；Worker 根据队列深度水平扩容。PostgreSQL、Redis、OSS 使用托管服务和备份策略。
5. 配置任务失败率、P95 耗时、队列堆积、ODPS 扫描量、磁盘/对象存储、下载失败率告警。

## 4. 数据量与异常处理

| 情况 | 用户可见行为 | 运维行为 |
| --- | --- | --- |
| CID 缺失/多个 CID | 不提交，提示输入一个编码 | 记录校验失败计数，不保存明细 |
| ODPS 权限/分区失败 | 返回脱敏失败提示与任务号 | 查实例 ID 和权限日志 |
| 明细超过行数上限 | 不生成截断 xlsx | 引导缩小范围或走异步 CSV/OSS 流程 |
| Worker 中断 | 任务保持可重试状态 | 根据幂等 job_id 重投，不重复生成文件 |
| 文件过期 | 返回 410 | 清理 OSS 对象和临时目录 |

## 5. 上线验收清单

- [ ] 真实 SQL 返回 `event_date`、`user_id`，且 PV/UV 口径经数据团队签字确认。
- [ ] 近 7 天分区的“今天”按 Asia/Shanghai 定义。
- [ ] 无 CID、多 CID、无数据、超限、ODPS 超时和企业微信回调失败均有可读响应。
- [ ] xlsx 有 `原始数据` 与 `聚合统计`，统计表按日期显示 PV/UV 并有总计。
- [ ] 回调验签、SSO、RBAC、私有 OSS、生命周期和审计下载均已启用。
- [ ] 统计后台可按日期、渠道、账号、IP、CID、任务状态查看请求/下载次数。
