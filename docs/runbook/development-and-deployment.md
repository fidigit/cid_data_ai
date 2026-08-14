# 开发、部署与验收手册

## 1. 凭证与配置

- 不在 `.env`、SQL、日志、Git 历史或企业微信群发送 AccessKey；`.env` 仅供本机测试。
- 生产从密钥服务注入短期 STS/RAM 凭证；授权仅限必要的 MaxCompute Project、固定源表和 Tunnel 下载。
- 设置 `DATA_SOURCE_TABLE`、字段名和 `sql/event_detail.sql` 后，先在低权限测试账号跑一条已知 CID。
- 企业微信上线前必须确定“智能机器人 API 模式”或“自建应用”，配置 HTTPS 回调、Token、EncodingAESKey、可信 IP，并以官方 SDK/协议验签与解密。普通群机器人 Webhook 只能作为通知出口。

## 2. xlsx 运行时

项目使用 `@oai/artifact-tool` 生成工作簿。发布镜像必须包含 Node.js 和经组织审核的该包，且运行时能从 `/app/scripts/build_report.mjs` 解析到 `/app/node_modules/@oai/artifact-tool`。本机验证可将工作区的 `node_modules` 指向受管运行时依赖目录；不要将该依赖目录复制或提交到仓库。

在本机执行：

```powershell
$env:SPREADSHEET_NODE_BIN = 'C:\\Users\\JOYY\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\bin\\node.exe'
pytest -q
```

## 3. 发布流程

1. 在 CI 跑 `pytest -q`，并用脱敏 fixture 生成一份 xlsx，使用 `scripts/verify_report.mjs` 检查两个 Sheet、汇总值、公式错误和渲染预览。
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

