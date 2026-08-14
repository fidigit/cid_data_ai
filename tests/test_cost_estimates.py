import pytest

from app.services.cost_estimates import (
    CostEstimateTokenError,
    issue_cost_estimate_token,
    verify_cost_estimate_token,
)


CLAIMS = {
    "secret": "test-secret",
    "requester_id": "user-1",
    "event_code": "90056_0001",
    "partition_start": "20260805",
    "partition_end": "20260811",
    "estimated_amount_cny": 1.2345,
}
VERIFY_CLAIMS = {key: value for key, value in CLAIMS.items() if key != "estimated_amount_cny"}


def test_cost_estimate_token_round_trip() -> None:
    token, expires_at = issue_cost_estimate_token(**CLAIMS, ttl_seconds=600, now=1000)
    claims = verify_cost_estimate_token(token, **VERIFY_CLAIMS, now=1001)
    assert claims.expires_at == expires_at == 1600
    assert claims.estimated_amount_cny == 1.2345


def test_cost_estimate_token_rejects_changed_question_context() -> None:
    token, _ = issue_cost_estimate_token(**CLAIMS, ttl_seconds=600, now=1000)
    with pytest.raises(CostEstimateTokenError, match="查询内容已变化"):
        verify_cost_estimate_token(
            token, **(VERIFY_CLAIMS | {"event_code": "90056_0002"}), now=1001
        )


def test_cost_estimate_token_rejects_expired_token() -> None:
    token, _ = issue_cost_estimate_token(**CLAIMS, ttl_seconds=10, now=1000)
    with pytest.raises(CostEstimateTokenError, match="已过期"):
        verify_cost_estimate_token(token, **VERIFY_CLAIMS, now=1010)


def test_cost_estimate_token_rejects_tampering() -> None:
    token, _ = issue_cost_estimate_token(**CLAIMS, ttl_seconds=600, now=1000)
    body, signature = token.split(".")
    tampered = f"{body[:-1]}A.{signature}"
    with pytest.raises(CostEstimateTokenError, match="校验失败"):
        verify_cost_estimate_token(tampered, **VERIFY_CLAIMS, now=1001)
