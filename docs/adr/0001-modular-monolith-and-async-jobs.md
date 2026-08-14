# ADR-0001: 使用模块化单体和异步任务队列

## Status

Accepted

## Context

ODPS 查询、明细下载和 xlsx 生成可能持续数分钟，不能占用企业微信回调或网页请求。V1 的业务域单一、并发尚未确定。

## Decision

使用一个 FastAPI 代码仓库，API 进程负责鉴权/建任务，Celery Worker 进程负责查询与导出，Redis 作任务队列，PostgreSQL 作审计库。

## Consequences

### Positive

- 部署、排障、权限管理简单；Worker 可按需独立扩容。
- 回调可快速返回“已受理”，避免平台超时。

### Negative

- 需要维护 Redis 与 Worker 的可靠投递、重试和幂等性。

## Alternatives Considered

- 同步 FastAPI：查询长、容易超时，拒绝。
- 微服务：V1 运维复杂度高，拒绝。
- 纯 DataWorks 调度：无法很好处理机器人逐条交互和文件回传，拒绝。

