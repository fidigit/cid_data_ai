from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


class CostEstimateTokenError(ValueError):
    pass


@dataclass(frozen=True)
class CostEstimateClaims:
    requester_id: str
    event_code: str
    partition_start: str
    partition_end: str
    estimated_amount_cny: float
    expires_at: int


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise CostEstimateTokenError("费用评估凭证格式无效，请重新评估。") from exc


def issue_cost_estimate_token(
    *,
    secret: str,
    requester_id: str,
    event_code: str,
    partition_start: str,
    partition_end: str,
    estimated_amount_cny: float,
    ttl_seconds: int,
    now: int | None = None,
) -> tuple[str, int]:
    if not secret:
        raise RuntimeError("费用评估签名密钥尚未配置。")
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + ttl_seconds
    payload = {
        "sub": requester_id,
        "cid": event_code,
        "start": partition_start,
        "end": partition_end,
        "amount": round(float(estimated_amount_cny), 4),
        "exp": expires_at,
    }
    body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _encode(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}", expires_at


def verify_cost_estimate_token(
    token: str,
    *,
    secret: str,
    requester_id: str,
    event_code: str,
    partition_start: str,
    partition_end: str,
    now: int | None = None,
) -> CostEstimateClaims:
    try:
        body, supplied_signature = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise CostEstimateTokenError("费用评估凭证格式无效，请重新评估。") from exc

    expected_signature = _encode(
        hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise CostEstimateTokenError("费用评估凭证校验失败，请重新评估。")

    try:
        payload = json.loads(_decode(body))
        claims = CostEstimateClaims(
            requester_id=str(payload["sub"]),
            event_code=str(payload["cid"]),
            partition_start=str(payload["start"]),
            partition_end=str(payload["end"]),
            estimated_amount_cny=float(payload["amount"]),
            expires_at=int(payload["exp"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CostEstimateTokenError("费用评估凭证内容无效，请重新评估。") from exc

    expected = (requester_id, event_code, partition_start, partition_end)
    actual = (
        claims.requester_id,
        claims.event_code,
        claims.partition_start,
        claims.partition_end,
    )
    if actual != expected:
        raise CostEstimateTokenError("查询内容已变化，请重新进行费用评估。")
    current_time = int(time.time()) if now is None else now
    if claims.expires_at <= current_time:
        raise CostEstimateTokenError("费用评估已过期，请重新评估。")
    return claims
