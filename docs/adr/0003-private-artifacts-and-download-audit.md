# ADR-0003: 结果文件私有存储并逐次记录下载

## Status

Accepted

## Context

明细文件可能含设备标识或其他内部数据，且产品需要统计下载行为。

## Decision

生产环境使用私有 OSS 存储，文件有生命周期；下载经受控端点或短期签名 URL 完成，每一次下载创建审计日志。

## Consequences

### Positive

- 文件不公开，能够统计下载次数、账号、IP 和时间。

### Negative

- 需要对象存储生命周期、签名 URL 和身份校验配置。

## Alternatives Considered

- 直接把本地文件长期暴露给 Nginx：审计与权限不完整，拒绝。

