# ADR-0002: CID 抽取采用规则优先

## Status

Accepted

## Context

V1 CID 格式为五位数字、下划线、四位数字；用户自然语言问法丰富，但数据查询不可误执行。

## Decision

先用确定性正则抽取 CID；仅在结果为唯一值时创建任务。无结果或多值时要求用户澄清。LLM 仅作为 V2 的中文名/截图候选工具，不能绕过格式和白名单检查。

## Consequences

### Positive

- 零模型成本，结果可解释、可测试；避免 prompt injection 影响 SQL。

### Negative

- 新编码格式需修改配置和测试；无法直接理解中文名称。

## Alternatives Considered

- 直接 LLM 抽取：不确定性和隐私成本高，拒绝作为 V1 主路径。

